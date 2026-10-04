import pandas as pd
import pytest
from technical_refs import frame

from app.domain.technical import PatternHit, PatternKey
from app.domain.technical.candlesticks import PATTERNS
from app.services import compute
from app.services.reports import PriceStatuses
from app.services.status import ok

STATUSES = PriceStatuses(prices=ok(), overall=ok())
N_BARS = 60
LAST = N_BARS - 1


def _frame() -> pd.DataFrame:
    return frame([(100.0 + i, 101.0 + i, 99.0 + i, 100.0 + i) for i in range(N_BARS)])


def _hit(df: pd.DataFrame, index: int, key: PatternKey = PatternKey.HAMMER) -> PatternHit:
    stamp = pd.Timestamp(df.index[index]).to_pydatetime().replace(tzinfo=None)
    return PatternHit(key, PATTERNS[key].bias, index, stamp)


def _technical(monkeypatch: pytest.MonkeyPatch, hits_at: list[int]):
    df = _frame()
    hits = [_hit(df, i) for i in hits_at]
    monkeypatch.setattr(compute, "detect_patterns", lambda _frame: hits)
    return df, compute.compute_technical("AAPL", df, STATUSES)


def test_compute_technical_no_recent_patterns_sets_latest_with_sessions_ago(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    df, report = _technical(monkeypatch, [10, 40])

    assert report.recent_patterns == []
    latest = report.latest_pattern
    assert latest is not None
    assert latest.sessions_ago == LAST - 40
    assert latest.date == pd.Timestamp(df.index[40]).date()
    assert latest.pattern == PatternKey.HAMMER.value
    assert latest.label == PATTERNS[PatternKey.HAMMER].label
    assert latest.bias == PATTERNS[PatternKey.HAMMER].bias.value


def test_compute_technical_recent_pattern_present_latest_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, report = _technical(monkeypatch, [10, LAST - 2])

    assert len(report.recent_patterns) == 1
    assert report.latest_pattern is None


def test_compute_technical_pattern_on_last_bar_is_recent_not_latest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, report = _technical(monkeypatch, [LAST])

    assert report.latest_pattern is None


def test_compute_technical_pattern_just_outside_window_has_sessions_ago_three(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, report = _technical(monkeypatch, [LAST - 3])

    assert report.recent_patterns == []
    assert report.latest_pattern is not None
    assert report.latest_pattern.sessions_ago == 3


def test_compute_technical_no_patterns_at_all_latest_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, report = _technical(monkeypatch, [])

    assert report.latest_pattern is None
