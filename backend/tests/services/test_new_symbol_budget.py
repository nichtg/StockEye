import asyncio
from datetime import timedelta

import pytest
from bson import ObjectId

from app.config import Settings
from app.db import Database
from app.repositories.ingest_budget import IngestBudget, install_indexes
from app.services.analysis import NEW_SYMBOL_LIMIT_REASON
from app.services.container import Services
from app.services.reports import MacroResponse
from tests.services.fakes import CLOSED_NOW, FakeClock, FakeNews

pytestmark = pytest.mark.integration

ALICE, BOB = ObjectId(), ObjectId()


@pytest.fixture
def settings(settings: Settings) -> Settings:
    settings.max_new_symbols_per_user_per_day = 1
    return settings


async def _macro_and_settle(services: Services, symbol: str, user: ObjectId) -> MacroResponse:
    response = await services.analysis.macro(symbol, user)
    await services.news.wait(symbol)
    return response


async def test_macro_first_new_symbol_of_the_day_starts_ingestion(services: Services) -> None:
    response = await _macro_and_settle(services, "AAPL", ALICE)

    assert response.ingestion.in_progress
    assert (await services.news.progress("AAPL")).months_done == 24


async def test_macro_past_the_daily_budget_reports_news_unavailable_without_ingesting(
    services: Services, news_provider: FakeNews
) -> None:
    await _macro_and_settle(services, "AAPL", ALICE)
    queries_before = len(news_provider.queries)

    response = await _macro_and_settle(services, "MSFT", ALICE)

    assert response.data_status.news.state == "unavailable"
    assert response.data_status.news.reason == NEW_SYMBOL_LIMIT_REASON
    assert response.report is not None  # prices still analysed; only the news is withheld
    assert not response.ingestion.in_progress
    assert len(news_provider.queries) == queries_before
    assert not await services.news.has_history("MSFT")


async def test_macro_refused_report_is_not_cached_so_the_next_day_can_succeed(
    services: Services, clock: FakeClock
) -> None:
    await _macro_and_settle(services, "AAPL", ALICE)
    await _macro_and_settle(services, "MSFT", ALICE)
    clock.now = CLOSED_NOW + timedelta(days=1)  # a new UTC day, a fresh budget

    response = await _macro_and_settle(services, "MSFT", ALICE)

    assert response.data_status.news.state != "unavailable"
    assert await services.news.has_history("MSFT")


async def test_macro_budget_is_per_user(services: Services) -> None:
    await _macro_and_settle(services, "AAPL", ALICE)

    response = await _macro_and_settle(services, "MSFT", BOB)

    assert response.data_status.news.state != "unavailable"


async def test_macro_symbol_someone_else_already_ingested_costs_no_budget(
    services: Services,
) -> None:
    await _macro_and_settle(services, "AAPL", ALICE)

    await _macro_and_settle(services, "AAPL", BOB)  # has history: free
    response = await _macro_and_settle(services, "MSFT", BOB)  # Bob's one new symbol

    assert response.data_status.news.state != "unavailable"


async def test_try_spend_is_idempotent_per_symbol_and_atomic_at_the_cap(db: Database) -> None:
    await install_indexes(db)
    budget = IngestBudget(db, per_day=5)

    results = await asyncio.gather(
        *(budget.try_spend(ALICE, f"SYM{n}", CLOSED_NOW) for n in range(30))
    )

    assert sum(results) == 5
    admitted = [n for n, ok in enumerate(results) if ok]
    assert await budget.try_spend(ALICE, f"SYM{admitted[0]}", CLOSED_NOW)  # already admitted
    assert not await budget.try_spend(ALICE, "NEW", CLOSED_NOW)


async def test_try_spend_with_a_zero_budget_admits_nothing(db: Database) -> None:
    await install_indexes(db)

    assert not await IngestBudget(db, per_day=0).try_spend(ALICE, "AAPL", CLOSED_NOW)
