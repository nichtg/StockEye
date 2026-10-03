"""Fixtures for service tests: real MongoDB, fake vendors, a controllable clock."""

import pytest

from app.config import Settings
from app.db import Database, ensure_indexes
from app.main import INDEX_INSTALLERS
from app.providers.resilience import ProviderGuard
from app.repositories.quotas import QuotaLedger
from app.services.analysis import AnalysisService
from app.services.container import Services
from app.services.market_data import MarketDataService
from app.services.news import NewsService
from tests.services.fakes import (
    FakeClock,
    FakeMarketData,
    FakeNews,
    FakeScorer,
)


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
def scorer() -> FakeScorer:
    return FakeScorer()


@pytest.fixture
async def services(
    db: Database,
    *,
    settings: Settings,
    clock: FakeClock,
    provider: FakeMarketData,
    news_provider: FakeNews,
    scorer: FakeScorer,
) -> Services:
    await ensure_indexes(db, INDEX_INSTALLERS)
    # The fake adapters are used unguarded; the guard only backs the admin status page.
    guard = ProviderGuard(
        QuotaLedger(db), settings.provider_limits, settings.quota_warning_ratio, clock=clock
    )
    market = MarketDataService(db, provider, clock)
    news = NewsService(db, news_provider, [news_provider], scorer, clock=clock)
    return Services(market, news, AnalysisService(db, market, news, clock), guard)
