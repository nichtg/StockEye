"""FinBERT sentiment scoring through ONNX Runtime (CPU) and the ``tokenizers`` library."""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from tokenizers import Tokenizer

from app.sentiment.scorer import SentimentScore, SentimentUnavailableError

_HINT = "Run `uv run python scripts/download_finbert.py` from backend/ to install the model."
_REQUIRED_FILES = ("model.onnx", "tokenizer.json", "config.json")
_LABELS = frozenset({"positive", "negative", "neutral"})
_MODEL_INPUTS = ("input_ids", "attention_mask", "token_type_ids")

# Builds an inference session (anything with get_inputs() and run()) from a model path. Injectable
# so tests need no real model; production uses onnxruntime on the CPU provider.
SessionFactory = Callable[[Path], Any]


def _default_session_factory(model_path: Path) -> Any:
    import onnxruntime as ort  # noqa: PLC0415 - deferred: importing it is slow

    return ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])


def softmax(logits: NDArray[np.float64]) -> NDArray[np.float64]:
    """Row-wise softmax, stabilised by subtracting the row max (avoids exp overflow)."""
    shifted = logits - logits.max(axis=-1, keepdims=True)
    exp = np.exp(shifted)
    result: NDArray[np.float64] = exp / exp.sum(axis=-1, keepdims=True)
    return result


@dataclass(frozen=True, slots=True)
class _Loaded:
    session: Any
    tokenizer: Tokenizer
    input_names: frozenset[str]
    # Column index of each class in the model's logits, taken from config.json.
    positive_idx: int
    negative_idx: int
    neutral_idx: int


class FinBertOnnxScorer:
    """Scores texts with a local FinBERT ONNX export. Thread-safe; loads lazily on first use."""

    def __init__(
        self,
        model_dir: Path,
        *,
        batch_size: int = 32,
        max_length: int = 128,
        session_factory: SessionFactory = _default_session_factory,
    ) -> None:
        if batch_size < 1:
            msg = "batch_size must be >= 1"
            raise ValueError(msg)
        self._model_dir = model_dir
        self._batch_size = batch_size
        self._max_length = max_length
        self._session_factory = session_factory
        self._load_lock = threading.Lock()
        self._loaded: _Loaded | None = None
        self._version: str | None = None

    @property
    def model_version(self) -> str:
        """``finbert-onnx:`` plus the first 12 hex chars of the sha256 of model.onnx."""
        if self._version is None:
            path = self._model_dir / "model.onnx"
            if not path.is_file():
                raise self._unavailable(f"missing {path}")
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(chunk)
            self._version = f"finbert-onnx:{digest.hexdigest()[:12]}"
        return self._version

    def score(self, texts: Sequence[str]) -> list[SentimentScore]:
        """Score each text; output order matches input. Empty input returns [] without loading."""
        if not texts:
            return []
        loaded = self._load()
        results: list[SentimentScore] = []
        for start in range(0, len(texts), self._batch_size):
            results.extend(self._score_batch(loaded, list(texts[start : start + self._batch_size])))
        return results

    @staticmethod
    def _unavailable(detail: str) -> SentimentUnavailableError:
        return SentimentUnavailableError(f"FinBERT model unavailable: {detail}. {_HINT}")

    def _load(self) -> _Loaded:
        loaded = self._loaded
        if loaded is not None:
            return loaded
        with self._load_lock:
            if self._loaded is None:
                self._loaded = self._load_unlocked()
            return self._loaded

    def _load_unlocked(self) -> _Loaded:
        for name in _REQUIRED_FILES:
            if not (self._model_dir / name).is_file():
                raise self._unavailable(f"missing {self._model_dir / name}")
        try:
            id2label = json.loads((self._model_dir / "config.json").read_text(encoding="utf-8"))[
                "id2label"
            ]
            label_to_idx = {str(label).lower(): int(idx) for idx, label in id2label.items()}
            if set(label_to_idx) != _LABELS:
                msg = f"unexpected labels {sorted(label_to_idx)}"
                raise ValueError(msg)  # noqa: TRY301 - funnelled into the corrupt-model error
            tokenizer = Tokenizer.from_file(str(self._model_dir / "tokenizer.json"))
            tokenizer.enable_truncation(max_length=self._max_length)
            pad_id = tokenizer.token_to_id("[PAD]") or 0
            tokenizer.enable_padding(pad_id=pad_id, pad_token="[PAD]")  # noqa: S106
            session = self._session_factory(self._model_dir / "model.onnx")
            input_names = frozenset(i.name for i in session.get_inputs())
        except SentimentUnavailableError:
            raise
        except Exception as exc:
            raise self._unavailable(f"corrupt model files ({exc})") from exc
        return _Loaded(
            session=session,
            tokenizer=tokenizer,
            input_names=input_names,
            positive_idx=label_to_idx["positive"],
            negative_idx=label_to_idx["negative"],
            neutral_idx=label_to_idx["neutral"],
        )

    @staticmethod
    def _score_batch(loaded: _Loaded, batch: list[str]) -> list[SentimentScore]:
        encodings = loaded.tokenizer.encode_batch(batch)
        features: dict[str, NDArray[np.int64]] = {
            "input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
            "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64),
            "token_type_ids": np.array([e.type_ids for e in encodings], dtype=np.int64),
        }
        feed = {name: features[name] for name in _MODEL_INPUTS if name in loaded.input_names}
        logits = np.asarray(loaded.session.run(None, feed)[0], dtype=np.float64)
        probs = softmax(logits)
        return [
            SentimentScore(
                positive=float(row[loaded.positive_idx]),
                negative=float(row[loaded.negative_idx]),
                neutral=float(row[loaded.neutral_idx]),
            )
            for row in probs
        ]
