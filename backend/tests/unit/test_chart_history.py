"""build_chart returns the full history; the range only sets ``visible_from``."""

import json
import time
from datetime import date

import numpy as np
import pandas as pd

from app.providers.models import CorporateEvent
from app.services import compute
from app.services.charts import INDICATORS
from app.services.reports import ChartData, FullStatuses
from app.services.status import DataStatus

OK = DataStatus(state="ok", as_of=None, reason=None)
STATUSES = FullStatuses(prices=OK, events=OK, news=OK, overall=OK)


def _frame(index: pd.DatetimeIndex) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    close = 100 + np.cumsum(rng.normal(0, 1, len(index)))
    return pd.DataFrame(
        {
            "open": close - 0.3,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": rng.integers(1_000, 9_000, len(index)).astype(float),
        },
        index=index,
    )


def _daily(rows: int = 760) -> pd.DataFrame:
    return _frame(pd.bdate_range(end="2026-10-02", periods=rows))


def _hourly(sessions: int = 40) -> pd.DataFrame:
    days = pd.bdate_range(end="2026-10-02", periods=sessions)
    stamps = [d + pd.Timedelta(hours=h) for d in days for h in (9, 10, 11, 12, 13, 14, 15)]
    return _frame(pd.DatetimeIndex(stamps))


def _chart(
    range_key: str,
    frame: pd.DataFrame,
    indicators: list[str] | None = None,
    events: list[CorporateEvent] | None = None,
) -> ChartData:
    return compute.build_chart(
        "AAPL",
        range_key,  # type: ignore[arg-type]
        indicators or [],
        frame=frame,
        events=events or [],
        news=[],
        statuses=STATUSES,
    )


def test_build_chart_daily_6m_returns_full_history_and_visible_from_is_range_start() -> None:
    frame = _daily()

    chart = _chart("6M", frame)

    last = frame.index[-1]
    expected = frame.index[frame.index >= last - pd.Timedelta(days=183)][0]
    assert len(chart.candles) == len(frame)
    assert chart.candles[0].time == frame.index[0].strftime("%Y-%m-%d")
    assert chart.visible_from == expected.strftime("%Y-%m-%d")
    assert any(c.time == chart.visible_from for c in chart.candles)


def test_build_chart_hourly_1w_visible_from_is_first_bar_of_fifth_last_session() -> None:
    frame = _hourly()

    chart = _chart("1W", frame)

    fifth_last = pd.DatetimeIndex(frame.index).normalize().unique()[-5]
    first_bar = frame.index[frame.index >= fifth_last][0]
    times = [c.time for c in chart.candles]
    assert len(chart.candles) == len(frame)
    assert chart.visible_from == times[list(frame.index).index(first_bar)]
    assert isinstance(chart.visible_from, int)
    assert times.index(chart.visible_from) > 0  # earlier sessions are present


def test_build_chart_daily_vwap_starts_at_visible_from_with_typical_price() -> None:
    frame = _daily()

    chart = _chart("1Y", frame, ["vwap"])

    vwap = chart.indicators["vwap"]
    anchor = next(c for c in chart.candles if c.time == chart.visible_from)
    assert vwap[0].time == chart.visible_from
    assert vwap[0].value == round((anchor.high + anchor.low + anchor.close) / 3, 4)


def test_build_chart_all_indicator_series_are_finite_and_start_after_warm_up() -> None:
    chart = _chart("1Y", _daily(), list(INDICATORS))

    assert chart.indicators
    for name, series in chart.indicators.items():
        assert series, name
        assert all(np.isfinite(p.value) for p in series), name
    assert chart.indicators["sma50"][0].time != chart.candles[0].time


def test_build_chart_markers_before_visible_from_are_kept() -> None:
    frame = _daily()
    old = frame.index[10].date()
    events = [CorporateEvent(kind="dividend", date=old, label="Dividend 0.25 USD")]

    chart = _chart("6M", frame, events=events)

    marker = next(m for m in chart.markers if m.kind == "dividend")
    assert isinstance(marker.time, str)
    assert marker.time == old.isoformat()
    assert marker.time < str(chart.visible_from)
    assert any(c.time == marker.time for c in chart.candles)


def test_build_chart_marker_on_missing_bar_is_dropped() -> None:
    events = [CorporateEvent(kind="dividend", date=date(2000, 1, 1), label="Dividend")]

    assert _chart("6M", _daily(), events=events).markers == []


def test_build_chart_three_year_daily_payload_is_small_and_fast() -> None:
    frame = _daily()

    started = time.perf_counter()
    chart = _chart("2Y", frame, list(INDICATORS))
    elapsed = time.perf_counter() - started

    size = len(json.dumps(chart.model_dump(mode="json")))
    assert size < 1_500_000
    assert elapsed < 1.0  # 300 ms locally; loose here so slow CI machines don't flake
