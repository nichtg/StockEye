"""Fixtures for service tests: real MongoDB, fake vendors, a controllable clock."""

import pytest

from app.config import Settings
from app.db import Database, ensure_indexes
from app.main import INDEX_INSTALLERS
from app.services.container import Services
from tests.services.fakes import (
    FakeClock,
    FakeMarketData,
    FakeNews,
    FakeScorer,
    build_fake_services,
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
    return build_fake_services(
        db, settings, clock=clock, provider=provider, news_provider=news_provider, scorer=scorer
    )
