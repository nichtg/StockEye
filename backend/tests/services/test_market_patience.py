"""Users do not wait behind a background job's flight; a clean-up never turns into a 404."""

import asyncio
from datetime import UTC, datetime

import pytest

from app.db import Database
from app.providers.models import Bar, Interval, Quote
from app.providers.quota import scheduled_calls
from app.services import market_data
from app.services.container import Services
from tests.services.fakes import FakeClock, FakeMarketData

pytestmark = pytest.mark.integration

TUESDAY = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _short_patience(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(market_data, "JOIN_PATIENCE", 0.05)


async def test_user_gets_the_saved_quote_while_a_scheduled_flight_is_still_running(
    services: Services, provider: FakeMarketData, clock: FakeClock
) -> None:
    await services.market.quote("AAPL")  # saved
    clock.now = TUESDAY  # the saved quote has expired
    gate = asyncio.Event()
    real = provider.quote

    async def slow(symbol: str) -> Quote:
        await gate.wait()  # a background job paced by the quota guard
        return await real(symbol)

    provider.quote = slow  # type: ignore[method-assign]  # test spy
    with scheduled_calls():
        background = asyncio.create_task(services.market.quote("AAPL"))
    await asyncio.sleep(0)

    quote, status = await asyncio.wait_for(services.market.quote("AAPL"), 2)

    assert quote.symbol == "AAPL"
    assert status.state == "stale"
    assert status.reason is not None
    assert "still running" in status.reason
    assert not background.done()  # the flight carries on for the job
    gate.set()
    await background


async def test_user_with_nothing_saved_keeps_waiting_for_the_flight(
    services: Services, provider: FakeMarketData
) -> None:
    gate = asyncio.Event()
    real = provider.quote

    async def slow(symbol: str) -> Quote:
        await gate.wait()
        return await real(symbol)

    provider.quote = slow  # type: ignore[method-assign]  # test spy
    with scheduled_calls():
        background = asyncio.create_task(services.market.quote("MSFT"))
    await asyncio.sleep(0)
    waiting = asyncio.create_task(services.market.quote("MSFT"))
    await asyncio.sleep(0.2)  # well past the patience

    assert not waiting.done()  # no data to show, so a slow answer beats none
    gate.set()
    quote, status = await waiting
    assert quote.symbol == "MSFT"
    assert status.state == "ok"
    await background


async def test_user_gets_saved_bars_while_a_scheduled_flight_is_still_running(
    services: Services, provider: FakeMarketData, clock: FakeClock
) -> None:
    await services.market.daily_history("AAPL")
    clock.now = TUESDAY  # new sessions exist, so a refresh is due
    gate = asyncio.Event()
    real = provider.bars

    async def slow(symbol: str, interval: Interval, start: datetime, end: datetime) -> list[Bar]:
        await gate.wait()
        return await real(symbol, interval, start, end)

    provider.bars = slow  # type: ignore[method-assign]  # test spy
    with scheduled_calls():
        background = asyncio.create_task(services.market.daily_history("AAPL"))
    await asyncio.sleep(0.01)

    frame, status = await asyncio.wait_for(services.market.daily_history("AAPL"), 2)

    assert len(frame) > 100
    assert status.state == "stale"
    gate.set()
    await background


async def test_fetch_state_without_bars_is_refetched_not_reported_unknown(
    services: Services, provider: FakeMarketData, db: Database
) -> None:
    await services.market.daily_history("AAPL")
    await db["price_bars"].delete_many({})  # a clean-up removed the bars but not the state

    frame, status = await services.market.daily_history("AAPL")

    assert len(frame) > 100
    assert status.state == "ok"
    assert provider.calls["bars"] == 2
