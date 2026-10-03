"""Tests for the FinBERT ONNX scorer: fake-session unit tests plus a real-model check."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace

from app.sentiment.finbert_onnx import FinBertOnnxScorer, softmax
from app.sentiment.scorer import SentimentUnavailableError

REAL_MODEL_DIR = Path(__file__).resolve().parents[3] / "models" / "finbert"
_REAL_MODEL_PRESENT = all(
    (REAL_MODEL_DIR / n).is_file() for n in ("model.onnx", "tokenizer.json", "config.json")
)


class _Input:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeSession:
    """Returns fixed logits per row and records every feed it receives."""

    def __init__(self, logits: list[float], input_names: tuple[str, ...]) -> None:
        self._logits = logits
        self._input_names = input_names
        self.feeds: list[dict[str, Any]] = []

    def get_inputs(self) -> list[_Input]:
        return [_Input(n) for n in self._input_names]

    def run(self, _outputs: object, feed: dict[str, Any]) -> list[Any]:
        self.feeds.append(feed)
        rows = len(feed["input_ids"])
        return [np.tile(np.array(self._logits, dtype=np.float32), (rows, 1))]


def _make_model_dir(root: Path, id2label: dict[str, str] | None = None) -> Path:
    labels = id2label or {"0": "positive", "1": "negative", "2": "neutral"}
    root.mkdir(parents=True, exist_ok=True)
    (root / "config.json").write_text(json.dumps({"id2label": labels}), encoding="utf-8")
    vocab = {"[PAD]": 0, "[UNK]": 1, "good": 2, "bad": 3, "very": 4}
    tok = Tokenizer(WordLevel(vocab, unk_token="[UNK]"))
    tok.pre_tokenizer = Whitespace()  # type: ignore[assignment]
    tok.save(str(root / "tokenizer.json"))
    (root / "model.onnx").write_bytes(b"fake-model-bytes")
    return root


def _scorer(model_dir: Path, session: FakeSession, **kwargs: Any) -> FinBertOnnxScorer:
    return FinBertOnnxScorer(model_dir, session_factory=lambda _p: session, **kwargs)


def test_softmax_large_logits_stays_finite_and_sums_to_one() -> None:
    logits = np.array([[1000.0, 999.0, -1000.0]])

    result = softmax(logits)

    assert np.all(np.isfinite(result))
    assert math.isclose(float(result.sum()), 1.0)
    assert result[0, 0] > result[0, 1] > result[0, 2]


def test_score_empty_input_returns_empty_list_without_loading(tmp_path: Path) -> None:
    scorer = FinBertOnnxScorer(tmp_path / "nope")

    assert scorer.score([]) == []


def test_score_missing_model_dir_raises_unavailable_with_download_hint(tmp_path: Path) -> None:
    scorer = FinBertOnnxScorer(tmp_path / "nope")

    with pytest.raises(SentimentUnavailableError, match=r"download_finbert\.py"):
        scorer.score(["good"])


def test_model_version_missing_model_raises_unavailable(tmp_path: Path) -> None:
    scorer = FinBertOnnxScorer(tmp_path / "nope")

    with pytest.raises(SentimentUnavailableError):
        _ = scorer.model_version


def test_score_corrupt_tokenizer_raises_unavailable(tmp_path: Path) -> None:
    model_dir = _make_model_dir(tmp_path / "m")
    (model_dir / "tokenizer.json").write_text("not json", encoding="utf-8")
    scorer = _scorer(model_dir, FakeSession([0, 0, 0], ("input_ids",)))

    with pytest.raises(SentimentUnavailableError):
        scorer.score(["good"])


def test_model_version_is_sha256_prefix_of_model_bytes(tmp_path: Path) -> None:
    model_dir = _make_model_dir(tmp_path / "m")
    scorer = _scorer(model_dir, FakeSession([0, 0, 0], ("input_ids",)))

    expected = hashlib.sha256(b"fake-model-bytes").hexdigest()[:12]

    assert scorer.model_version == f"finbert-onnx:{expected}"


@pytest.mark.parametrize(
    "id2label",
    [
        {"0": "positive", "1": "negative", "2": "neutral"},
        {"0": "neutral", "1": "positive", "2": "negative"},
        {"0": "negative", "1": "neutral", "2": "positive"},
    ],
)
def test_score_label_order_from_config_maps_logits_correctly(
    tmp_path: Path, id2label: dict[str, str]
) -> None:
    model_dir = _make_model_dir(tmp_path / "m", id2label)
    # Column 1 dominates; the label of column 1 must win whatever the order is.
    scorer = _scorer(model_dir, FakeSession([0.0, 5.0, 0.0], ("input_ids",)))

    (result,) = scorer.score(["good"])

    probs = {"positive": result.positive, "negative": result.negative, "neutral": result.neutral}
    assert max(probs, key=lambda k: probs[k]) == id2label["1"]
    assert math.isclose(sum(probs.values()), 1.0)
    assert math.isclose(result.score, result.positive - result.negative)


def test_score_feeds_only_inputs_the_session_declares(tmp_path: Path) -> None:
    session = FakeSession([1.0, 0.0, 0.0], ("input_ids", "attention_mask"))
    scorer = _scorer(_make_model_dir(tmp_path / "m"), session)

    scorer.score(["good bad"])

    assert set(session.feeds[0]) == {"input_ids", "attention_mask"}


def test_score_batching_splits_inputs_and_preserves_count(tmp_path: Path) -> None:
    session = FakeSession([1.0, 0.0, 0.0], ("input_ids", "attention_mask", "token_type_ids"))
    scorer = _scorer(_make_model_dir(tmp_path / "m"), session, batch_size=2)

    results = scorer.score(["good", "bad", "very good", "bad", "good"])

    assert [len(f["input_ids"]) for f in session.feeds] == [2, 2, 1]
    assert len(results) == 5


def test_score_pads_to_longest_text_in_batch(tmp_path: Path) -> None:
    session = FakeSession([1.0, 0.0, 0.0], ("input_ids", "attention_mask"))
    scorer = _scorer(_make_model_dir(tmp_path / "m"), session)

    scorer.score(["good", "very very good"])

    feed = session.feeds[0]
    assert feed["input_ids"].shape == (2, 3)
    assert feed["attention_mask"].tolist() == [[1, 0, 0], [1, 1, 1]]


def test_score_truncates_to_max_length(tmp_path: Path) -> None:
    session = FakeSession([1.0, 0.0, 0.0], ("input_ids",))
    scorer = _scorer(_make_model_dir(tmp_path / "m"), session, max_length=3)

    scorer.score(["good " * 10])

    assert session.feeds[0]["input_ids"].shape == (1, 3)


@pytest.fixture(scope="module")
def scorer() -> FinBertOnnxScorer:
    return FinBertOnnxScorer(REAL_MODEL_DIR)


@pytest.mark.skipif(not _REAL_MODEL_PRESENT, reason="run scripts/download_finbert.py first")
class TestRealModel:
    def test_score_bullish_headline_is_clearly_positive(self, scorer: FinBertOnnxScorer) -> None:
        text = "Company beats earnings expectations and raises full-year guidance"

        (result,) = scorer.score([text])

        assert result.score > 0.3

    def test_score_bearish_headline_is_clearly_negative(self, scorer: FinBertOnnxScorer) -> None:
        text = "Company shares plunge after accounting fraud probe and CEO resignation"

        (result,) = scorer.score([text])

        assert result.score < -0.3

    def test_score_routine_headline_is_mostly_neutral(self, scorer: FinBertOnnxScorer) -> None:
        (result,) = scorer.score(["Company will hold its annual general meeting on Tuesday"])

        assert abs(result.score) < 0.5
        assert result.neutral > max(result.positive, result.negative)

    def test_model_version_has_expected_format(self, scorer: FinBertOnnxScorer) -> None:
        assert scorer.model_version.startswith("finbert-onnx:")
        assert len(scorer.model_version) == len("finbert-onnx:") + 12
