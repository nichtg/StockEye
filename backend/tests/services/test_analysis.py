from datetime import timedelta
from typing import Any

import pytest
from bson import ObjectId

from app.db import Database
from app.providers.errors import RateLimitedError, TransientProviderError
from app.repositories.cache import CacheRepository
from app.repositories.news import NewsRepository
from app.services import compute
from app.services.analysis import macro_cache_key
from app.services.container import Services
from app.services.errors import AppError
from tests.services.fakes import CLOSED_NOW, FakeClock, FakeMarketData, FakeNews, FakeScorer

pytestmark = pytest.mark.integration

USER = ObjectId()


async def test_technical_returns_outlook_patterns_and_ok_status(services: Services) -> None:
    report = await services.analysis.technical("AAPL")

    assert report.symbol == "AAPL"
    assert report.outlook.lean in {"bullish", "bearish", "neutral"}
    assert -1.0 <= report.outlook.score <= 1.0
    assert report.outlook.signals
    assert all(s.detail for s in report.outlook.signals)
    assert report.outlook.expected_range is not None
    assert report.outlook.expected_range.low < report.outlook.last_close
    assert report.outlook.as_of.isoformat() == "2026-10-02"
    assert report.data_status.prices.state == "ok"
    assert report.data_status.overall.state == "ok"


async def test_technical_recent_patterns_are_within_last_three_sessions(
    services: Services,
) -> None:
    report = await services.analysis.technical("AAPL")

    cutoff = report.outlook.as_of - timedelta(days=7)
    assert all(p.date > cutoff for p in report.recent_patterns)
    for pattern in report.recent_patterns:
        if pattern.stats is not None:
            assert pattern.stats.label
            assert pattern.stats.bias == pattern.bias


async def test_technical_second_call_is_cached_and_does_not_refetch(
    services: Services, provider: FakeMarketData
) -> None:
    first = await services.analysis.technical("AAPL")
    calls = dict(provider.calls)

    second = await services.analysis.technical("AAPL")

    assert provider.calls == calls
    assert second.outlook == first.outlook


async def test_technical_with_stale_prices_reports_stale_status(
    services: Services, provider: FakeMarketData, clock: FakeClock
) -> None:
    await services.analysis.technical("AAPL")
    clock.now = CLOSED_NOW + timedelta(days=3, hours=5)
    provider.fail_with = RateLimitedError("yahoo")

    report = await services.analysis.technical("AAPL")

    assert report.data_status.prices.state == "stale"
    assert report.data_status.overall.state == "stale"


async def test_technical_unknown_symbol_raises_not_found(services: Services) -> None:
    with pytest.raises(AppError) as caught:
        await services.analysis.technical("ZZZZ")

    assert caught.value.status == 404


async def test_chart_daily_indicators_have_no_nan_gap_at_left_edge(services: Services) -> None:
    chart = await services.analysis.chart(
        "AAPL", "6M", ["sma50", "sma20", "rsi", "bollinger", "macd"]
    )

    first_candle = chart.candles[0].time
    assert chart.interval == "1d"
    assert isinstance(first_candle, str)
    for name in ("sma50", "sma20", "rsi", "bollinger_upper", "macd", "macd_signal"):
        series = chart.indicators[name]
        assert series, name
        assert series[0].time == first_candle  # warm-up history fills the left edge
        assert len(series) == len(chart.candles)


async def test_chart_daily_range_covers_about_six_months(services: Services) -> None:
    chart = await services.analysis.chart("AAPL", "6M", [])

    assert 120 <= len(chart.candles) <= 135
    assert chart.indicators == {}


async def test_chart_1w_uses_hourly_bars_over_five_sessions_with_epoch_times(
    services: Services,
) -> None:
    chart = await services.analysis.chart("AAPL", "1W", ["sma20", "vwap"])

    assert chart.interval == "1h"
    assert all(isinstance(c.time, int) for c in chart.candles)
    days = {c.time // 86400 for c in chart.candles if isinstance(c.time, int)}
    assert len(days) == 5
    assert len(chart.indicators["sma20"]) == len(chart.candles)
    assert len(chart.indicators["vwap"]) == len(chart.candles)


async def test_chart_1m_shows_22_sessions_of_hourly_bars(services: Services) -> None:
    chart = await services.analysis.chart("AAPL", "1M", [])

    days = {c.time // 86400 for c in chart.candles if isinstance(c.time, int)}
    assert chart.interval == "1h"
    assert len(days) == 22


async def test_chart_daily_vwap_is_anchored_at_range_start(services: Services) -> None:
    chart = await services.analysis.chart("AAPL", "6M", ["vwap"])

    vwap = chart.indicators["vwap"]
    assert vwap[0].time == chart.candles[0].time
    first_bar = chart.candles[0]
    typical = (first_bar.high + first_bar.low + first_bar.close) / 3
    assert vwap[0].value == pytest.approx(typical)


async def test_chart_markers_include_events_and_patterns_on_daily_ranges(
    services: Services,
) -> None:
    chart = await services.analysis.chart("AAPL", "2Y", [])

    kinds = {m.kind for m in chart.markers}
    assert {"earnings", "dividend"} <= kinds
    assert "pattern" in kinds
    pattern = next(m for m in chart.markers if m.kind == "pattern")
    assert pattern.pattern
    assert pattern.bias in {"bullish", "bearish", "neutral"}
    assert all(isinstance(m.time, str) for m in chart.markers)


async def test_chart_hourly_ranges_have_no_pattern_markers(services: Services) -> None:
    chart = await services.analysis.chart("AAPL", "1M", [])

    assert "pattern" not in {m.kind for m in chart.markers}


async def test_chart_unknown_indicator_is_rejected(services: Services) -> None:
    with pytest.raises(AppError) as caught:
        await services.analysis.chart("AAPL", "6M", ["sma20", "nonsense"])

    assert caught.value.status == 422


async def test_chart_never_triggers_macro_computation(
    services: Services, news_provider: FakeNews
) -> None:
    await services.analysis.chart("AAPL", "2Y", [])

    assert news_provider.queries == []


async def test_chart_includes_news_markers_from_cached_macro_report(services: Services) -> None:
    await services.news.ensure_ingested("AAPL", "Apple Inc.")
    await services.news.wait("AAPL")
    macro = await services.analysis.macro("AAPL", USER)
    assert macro.report is not None
    assert macro.report.top_events
    assert macro.report.events

    chart = await services.analysis.chart("AAPL", "2Y", [])

    news = [m for m in chart.markers if m.kind == "news"]
    assert news
    assert all(m.car_0_1 is not None for m in news)
    # Markers cover every evaluated event, not just the 10 largest moves.
    assert sorted(m.time for m in news) == [e.date.isoformat() for e in macro.report.events]
    assert chart.data_status.news.state == "ok"


async def test_macro_first_call_reports_ingestion_in_progress_and_partial_news(
    services: Services,
) -> None:
    response = await services.analysis.macro("AAPL", USER)

    assert response.ingestion.in_progress
    assert response.ingestion.months_total == 24
    assert response.data_status.news.state == "partial"
    assert response.data_status.news.reason is not None
    assert "Collecting news" in response.data_status.news.reason


async def test_macro_after_ingestion_has_report_and_is_cached(
    services: Services, news_provider: FakeNews
) -> None:
    await services.news.ensure_ingested("AAPL", "Apple Inc.")
    await services.news.wait("AAPL")

    first = await services.analysis.macro("AAPL", USER)
    queries = len(news_provider.queries)
    second = await services.analysis.macro("AAPL", USER)

    assert not first.ingestion.in_progress
    assert first.ingestion.months_done == 24
    assert first.report is not None
    assert first.report.events_total > 0
    assert first.report.timeline
    assert first.data_status.overall.state == "ok"
    assert second == first
    assert len(news_provider.queries) == queries


async def test_macro_is_not_cached_while_ingestion_is_in_progress(services: Services) -> None:
    first = await services.analysis.macro("AAPL", USER)
    assert first.ingestion.in_progress

    await services.news.wait("AAPL")
    second = await services.analysis.macro("AAPL", USER)

    assert second.ingestion.months_done == 24
    assert not second.ingestion.in_progress


async def test_macro_with_sentiment_model_missing_degrades_instead_of_failing(
    services: Services, scorer: FakeScorer
) -> None:
    scorer.available = False
    await services.news.ensure_ingested("AAPL", "Apple Inc.")
    await services.news.wait("AAPL")

    response = await services.analysis.macro("AAPL", USER)

    assert response.data_status.news.state == "unavailable"
    assert response.report is not None
    assert response.report.events_total == 0
    assert response.data_status.overall.state == "partial"


async def test_macro_without_benchmark_data_returns_no_report_but_no_error(
    services: Services, provider: FakeMarketData
) -> None:
    provider.fail_symbols["SPY"] = TransientProviderError("yahoo", "down")

    response = await services.analysis.macro("AAPL", USER)

    assert response.report is None
    assert response.data_status.prices.state == "partial"
    assert response.data_status.prices.reason is not None
    assert "benchmark" in response.data_status.prices.reason


async def test_macro_sgx_symbol_uses_sti_benchmark(services: Services) -> None:
    await services.news.ensure_ingested("D05.SI", "DBS Group Holdings Ltd")
    await services.news.wait("D05.SI")

    response = await services.analysis.macro("D05.SI", USER)

    assert response.report is not None
    assert response.name == "DBS Group Holdings Ltd"


async def test_chart_without_cached_macro_report_builds_news_markers_from_stored_articles(
    services: Services, news_provider: FakeNews, db: Database
) -> None:
    await services.news.ensure_ingested("AAPL", "Apple Inc.")
    await services.news.wait("AAPL")
    queries = len(news_provider.queries)

    chart = await services.analysis.chart("AAPL", "2Y", [])

    news = [m for m in chart.markers if m.kind == "news"]
    assert news
    assert len(news_provider.queries) == queries  # read-only: no collection started
    assert await CacheRepository(db).lookup(macro_cache_key("AAPL")) is not None  # complete + ok


async def test_chart_news_markers_from_partial_build_are_not_cached(
    services: Services, news_provider: FakeNews, db: Database
) -> None:
    news_provider.fail_windows = {"2025-03"}
    await services.news.ensure_ingested("AAPL", "Apple Inc.")
    await services.news.wait("AAPL")

    chart = await services.analysis.chart("AAPL", "2Y", [])

    assert [m for m in chart.markers if m.kind == "news"]
    assert await CacheRepository(db).lookup(macro_cache_key("AAPL")) is None


async def test_chart_macro_build_failure_yields_no_news_markers_but_returns_chart(
    services: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    await services.news.ensure_ingested("AAPL", "Apple Inc.")
    await services.news.wait("AAPL")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("compute failed")

    monkeypatch.setattr(compute, "compute_macro", boom)

    chart = await services.analysis.chart("AAPL", "2Y", [])

    assert chart.candles
    assert not [m for m in chart.markers if m.kind == "news"]


async def test_news_progress_starts_collection_once_and_reports_status(
    services: Services, news_provider: FakeNews
) -> None:
    first = await services.analysis.news_progress("AAPL", USER)
    second = await services.analysis.news_progress("AAPL", USER)
    await services.news.wait("AAPL")

    assert first.in_progress
    assert second.in_progress
    assert first.status.state == "partial"
    assert len([q for q in news_provider.queries if q.start.day == 1]) == 24
    assert (await services.analysis.news_progress("AAPL", USER)).status.state == "ok"


async def test_news_progress_unknown_symbol_is_404_and_starts_nothing(
    services: Services, news_provider: FakeNews
) -> None:
    with pytest.raises(AppError) as caught:
        await services.analysis.news_progress("ZZZZ", USER)

    assert caught.value.status == 404
    assert news_provider.queries == []
    assert not await services.news.has_history("ZZZZ")


def _count_macro_builds(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []
    real = compute.compute_macro

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(compute, "compute_macro", counting)
    return calls


async def _partial_ingest(services: Services, news_provider: FakeNews) -> None:
    news_provider.fail_windows = {
        "2025-03",
        "2025-04",
    }  # incomplete, so the macro report is never cached
    await services.news.ensure_ingested("AAPL", "Apple Inc.")
    await services.news.wait("AAPL")


async def test_chart_partial_news_markers_are_cached_so_a_second_call_does_not_rebuild(
    services: Services, news_provider: FakeNews, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _partial_ingest(services, news_provider)
    builds = _count_macro_builds(monkeypatch)

    first = await services.analysis.chart("AAPL", "2Y", [])
    second = await services.analysis.chart("AAPL", "2Y", [])

    assert len(builds) == 1
    assert [m for m in first.markers if m.kind == "news"]
    assert second.markers == first.markers


async def test_chart_news_markers_rebuild_when_months_done_or_updated_at_changes(
    services: Services,
    news_provider: FakeNews,
    db: Database,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _partial_ingest(services, news_provider)
    builds = _count_macro_builds(monkeypatch)
    repo = NewsRepository(db)
    await services.analysis.chart("AAPL", "2Y", [])

    await repo.mark_month_done("AAPL", "2025-03")  # months_done changes, within the TTL
    await services.analysis.chart("AAPL", "2Y", [])
    await repo.mark_incremental("AAPL", clock.now + timedelta(minutes=1))  # updated_at changes
    await services.analysis.chart("AAPL", "2Y", [])

    assert len(builds) == 3


async def test_chart_symbol_without_news_never_builds_a_macro_report(
    services: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    builds = _count_macro_builds(monkeypatch)

    chart = await services.analysis.chart("AAPL", "2Y", [])

    assert builds == []
    assert chart.candles
    assert not [m for m in chart.markers if m.kind == "news"]


async def test_news_progress_provider_down_for_known_symbol_still_starts_collection(
    services: Services, provider: FakeMarketData, news_provider: FakeNews
) -> None:
    provider.fail_symbols["AAPL"] = TransientProviderError("yahoo", "down")  # no cached quote

    progress = await services.analysis.news_progress("AAPL", USER)
    await services.news.wait("AAPL")

    assert progress.in_progress
    assert news_provider.queries  # collection ran despite the quote failure
