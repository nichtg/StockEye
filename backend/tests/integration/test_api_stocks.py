from collections.abc import AsyncIterator
from datetime import timedelta

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

from app.config import Settings
from app.db import Database
from app.main import create_app
from app.providers.errors import RateLimitedError, TransientProviderError
from app.providers.resilience import ProviderGuard
from app.repositories.quotas import QuotaLedger
from app.services.analysis import AnalysisService
from app.services.container import Services
from app.services.market_data import MarketDataService
from app.services.news import NewsService
from tests.integration.conftest import ClientFactory, login, make_admin, register
from tests.services.fakes import (
    CLOSED_NOW,
    FakeClock,
    FakeMarketData,
    FakeNews,
    FakeScorer,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def provider(clock: FakeClock) -> FakeMarketData:
    return FakeMarketData(clock)


@pytest.fixture
def news_provider() -> FakeNews:
    return FakeNews()


@pytest.fixture
async def app(
    settings: Settings,
    db: Database,
    clock: FakeClock,
    provider: FakeMarketData,
    news_provider: FakeNews,
) -> AsyncIterator[FastAPI]:
    """The real app, with its services built around fake vendors."""

    async def factory(cfg: Settings, database: Database) -> Services:
        guard = ProviderGuard(
            QuotaLedger(database), cfg.provider_limits, cfg.quota_warning_ratio, clock=clock
        )
        market = MarketDataService(database, provider, clock)
        news = NewsService(database, news_provider, [news_provider], FakeScorer(), clock=clock)
        return Services(market, news, AnalysisService(database, market, news, clock), guard)

    application = create_app(settings, services_factory=factory)
    async with LifespanManager(application):
        yield application


@pytest.fixture
async def user(client: httpx.AsyncClient) -> httpx.AsyncClient:
    assert (await register(client, "alice@example.com")).status_code == 201
    return client


async def test_stocks_endpoints_without_session_return_401(client: httpx.AsyncClient) -> None:
    for path in ("/api/stocks/AAPL", "/api/stocks/AAPL/technical", "/api/watchlist/overview"):
        assert (await client.get(path)).status_code == 401


async def test_stock_detail_returns_quote_and_status(user: httpx.AsyncClient) -> None:
    resp = await user.get("/api/stocks/D05.SI")

    body = resp.json()
    assert resp.status_code == 200
    assert body["symbol"] == "D05.SI"
    assert body["exchange"] == "SGX"
    assert body["currency"] == "SGD"
    assert body["data_status"]["state"] == "ok"
    assert isinstance(body["change_pct"], float)


async def test_search_returns_matches_and_blank_query_returns_empty_list(
    user: httpx.AsyncClient,
) -> None:
    hit = await user.get("/api/stocks/search", params={"q": "apple"})
    blank = await user.get("/api/stocks/search", params={"q": ""})

    assert hit.status_code == 200
    assert [m["symbol"] for m in hit.json()] == ["AAPL"]
    assert blank.json() == []


async def test_technical_returns_outlook_with_data_status(user: httpx.AsyncClient) -> None:
    resp = await user.get("/api/stocks/AAPL/technical")

    body = resp.json()
    assert resp.status_code == 200
    assert body["outlook"]["lean"] in {"bullish", "bearish", "neutral"}
    assert body["outlook"]["signals"][0]["detail"]
    assert set(body["data_status"]) == {"prices", "overall"}
    assert body["data_status"]["prices"]["state"] == "ok"
    assert isinstance(body["recent_patterns"], list)


async def test_chart_returns_candles_and_requested_indicators(user: httpx.AsyncClient) -> None:
    resp = await user.get(
        "/api/stocks/D05.SI/chart", params={"range": "6M", "indicators": "sma20,rsi"}
    )

    body = resp.json()
    assert resp.status_code == 200
    assert body["interval"] == "1d"
    assert set(body["indicators"]) == {"sma20", "rsi"}
    assert len(body["indicators"]["sma20"]) == len(body["candles"])
    assert set(body["data_status"]) == {"prices", "events", "news", "overall"}
    assert isinstance(body["candles"][0]["time"], str)


async def test_chart_hourly_range_uses_epoch_seconds(user: httpx.AsyncClient) -> None:
    resp = await user.get("/api/stocks/AAPL/chart", params={"range": "1W"})

    assert resp.status_code == 200
    assert isinstance(resp.json()["candles"][0]["time"], int)


async def test_chart_rejects_unknown_range_and_indicator(user: httpx.AsyncClient) -> None:
    bad_range = await user.get("/api/stocks/AAPL/chart", params={"range": "5Y"})
    bad_indicator = await user.get("/api/stocks/AAPL/chart", params={"indicators": "sma20,wat"})

    assert bad_range.status_code == 422
    assert bad_indicator.status_code == 422
    assert bad_indicator.json()["error"]["code"] == "validation_error"


async def test_symbol_must_be_uppercase_and_well_formed(user: httpx.AsyncClient) -> None:
    assert (await user.get("/api/stocks/aapl/technical")).status_code == 422
    assert (await user.get("/api/stocks/BAD$SYMBOL/technical")).status_code == 422


async def test_unknown_symbol_returns_404_envelope(user: httpx.AsyncClient) -> None:
    resp = await user.get("/api/stocks/ZZZZ/technical")

    assert resp.status_code == 404
    error = resp.json()["error"]
    assert error["code"] == "not_found"
    assert "ZZZZ" in error["message"]


async def test_prices_unavailable_with_empty_cache_returns_503_not_500(
    user: httpx.AsyncClient, provider: FakeMarketData
) -> None:
    provider.fail_with = TransientProviderError("yahoo", "down")

    resp = await user.get("/api/stocks/AAPL/technical")

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "data_unavailable"


async def test_provider_failure_with_cache_serves_stale_data_with_status(
    user: httpx.AsyncClient, provider: FakeMarketData, clock: FakeClock
) -> None:
    assert (await user.get("/api/stocks/AAPL/technical")).status_code == 200
    clock.now = CLOSED_NOW + timedelta(days=3, hours=5)
    provider.fail_with = RateLimitedError("yahoo")

    resp = await user.get("/api/stocks/AAPL/technical")

    status = resp.json()["data_status"]["prices"]
    assert resp.status_code == 200
    assert status["state"] == "stale"
    assert "Yahoo Finance hit its rate limit" in status["reason"]


async def test_macro_reports_ingestion_progress_then_completes(
    user: httpx.AsyncClient, app: FastAPI
) -> None:
    first = await user.get("/api/stocks/AAPL/macro")
    assert first.status_code == 200
    assert first.json()["ingestion"]["in_progress"] is True
    assert first.json()["data_status"]["news"]["state"] == "partial"

    await app.state.services.news.wait("AAPL")
    done = (await user.get("/api/stocks/AAPL/macro")).json()

    assert done["ingestion"] == {"months_done": 24, "months_total": 24, "in_progress": False}
    assert done["report"]["events_total"] > 0
    assert set(done["report"]["stats_all"]["buckets"]) == {"positive", "neutral", "negative"}
    assert done["data_status"]["overall"]["state"] == "ok"


async def test_watchlist_overview_one_failing_symbol_does_not_fail_the_list(
    user: httpx.AsyncClient,
) -> None:
    for symbol in ("AAPL", "ZZZZ", "D05.SI"):
        assert (await user.put(f"/api/watchlist/{symbol}")).status_code == 200

    resp = await user.get("/api/watchlist/overview")

    assert resp.status_code == 200
    rows = {r["symbol"]: r for r in resp.json()}
    assert set(rows) == {"AAPL", "ZZZZ", "D05.SI"}
    assert rows["AAPL"]["status"] == "ok"
    assert len(rows["AAPL"]["sparkline"]) == 20
    assert rows["ZZZZ"]["status"] == "unavailable"
    assert rows["ZZZZ"]["last_price"] is None
    assert rows["D05.SI"]["exchange"] == "SGX"


async def test_watchlist_overview_empty_watchlist_returns_empty_list(
    user: httpx.AsyncClient,
) -> None:
    assert (await user.get("/api/watchlist/overview")).json() == []


async def test_admin_providers_returns_status_for_every_provider(
    new_client: ClientFactory, db: Database
) -> None:
    await make_admin(db)
    admin = await new_client()
    assert (await login(admin, "root@example.com")).status_code == 200

    resp = await admin.get("/api/admin/providers")

    rows = {r["provider"]: r for r in resp.json()}
    assert resp.status_code == 200
    assert set(rows) == {"yahoo", "google_news", "finnhub", "alphavantage", "marketaux"}
    assert set(rows["yahoo"]) == {
        "provider",
        "configured",
        "used_today",
        "daily_limit",
        "used_ratio",
        "resets_at",
        "breaker_state",
        "last_error",
        "last_error_at",
        "level",
        "message",
    }
    assert rows["yahoo"]["configured"] is True
    assert rows["finnhub"]["configured"] is False


async def test_admin_providers_for_normal_user_returns_403(user: httpx.AsyncClient) -> None:
    resp = await user.get("/api/admin/providers")

    assert resp.status_code == 403
