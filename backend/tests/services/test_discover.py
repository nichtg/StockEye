import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.db import Database
from app.providers.errors import TransientProviderError
from app.providers.models import ScreenMatch, ScreenQuery
from app.providers.quota import current_priority
from app.repositories.cache import COLLECTION, CacheRepository
from app.services.container import Services
from app.services.discover import (
    CACHE_KEY,
    CACHE_TTL,
    EMPTY_REASON,
    PRESETS,
    ROWS_PER_LIST,
    SCREEN_SIZE,
    is_overdue,
    last_scheduled_build,
)
from tests.services.fakes import FakeClock, FakeMarketData

pytestmark = pytest.mark.integration

US = ["AAPL", "MSFT"]
SG = ["D05.SI"]


@pytest.fixture(autouse=True)
def _hits(provider: FakeMarketData) -> None:
    provider.screen_hits = {"us": US, "sg": SG}


async def test_refresh_builds_three_lists_with_full_rows(services: Services) -> None:
    await services.discover.refresh()

    page = await services.discover.lists()

    assert [lst.id for lst in page.lists] == [p.id for p in PRESETS]
    assert len(PRESETS) == 3
    for lst in page.lists[:2]:
        assert [r.symbol for r in lst.rows] == US
        assert lst.status.state == "ok"
    assert [r.symbol for r in page.lists[2].rows] == SG
    row = page.lists[0].rows[0]
    assert row.country == "United States"
    assert row.sector == "Technology"
    assert row.market_cap == 2.5e9
    assert page.data_status.state == "ok"
    assert page.updated_at is not None


async def test_refresh_asks_the_screener_for_more_than_it_shows(
    services: Services, provider: FakeMarketData
) -> None:
    sizes: list[int] = []
    real = provider.screen

    async def spy(query: ScreenQuery) -> list[ScreenMatch]:
        sizes.append(query.size)
        return await real(query)

    provider.screen = spy  # type: ignore[method-assign]  # test spy

    await services.discover.refresh()

    assert sizes == [SCREEN_SIZE] * 3
    assert SCREEN_SIZE > ROWS_PER_LIST


async def test_refresh_keeps_only_the_first_fifteen_rows_that_build(
    services: Services, provider: FakeMarketData
) -> None:
    provider.screen_hits = {"us": ["ZZZZ"] + [f"S{n}" for n in range(24)], "sg": []}

    await services.discover.refresh()

    page = await services.discover.lists()
    first = page.lists[0]
    assert len(first.rows) == ROWS_PER_LIST
    assert first.rows[0].symbol == "S0"  # the unbuildable first hit was skipped
    assert first.status.state == "ok"  # 15 built, so nothing was lost


async def test_list_that_lost_some_rows_is_marked_stale_with_a_plain_reason(
    services: Services, provider: FakeMarketData
) -> None:
    provider.screen_hits = {"us": ["AAPL", "ZZZZ", "MSFT"], "sg": SG}  # ZZZZ cannot be built

    await services.discover.refresh()

    page = await services.discover.lists()
    lost = page.lists[0]
    assert [r.symbol for r in lost.rows] == ["AAPL", "MSFT"]
    assert lost.status.state == "stale"
    assert lost.status.reason == "Some stocks in this list could not be loaded tonight."
    assert page.lists[2].status.state == "ok"
    assert page.data_status.state == "stale"


async def test_refresh_makes_every_vendor_call_as_scheduled_work(
    services: Services, provider: FakeMarketData
) -> None:
    seen: dict[str, set[str]] = {}

    def spy(name: str) -> None:
        real = getattr(provider, name)

        async def wrapper(*args: object) -> object:
            seen.setdefault(name, set()).add(current_priority())
            return await real(*args)

        setattr(provider, name, wrapper)

    for name in ("screen", "bars", "quote", "profile"):
        spy(name)

    await services.discover.refresh()

    assert seen == {name: {"scheduled"} for name in ("screen", "bars", "quote", "profile")}


async def test_refresh_builds_one_row_at_a_time(
    services: Services, provider: FakeMarketData
) -> None:
    active = peak = 0
    real = provider.quote

    async def spy(symbol: str):  # type: ignore[no-untyped-def]  # test spy
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0)
            return await real(symbol)
        finally:
            active -= 1

    provider.quote = spy  # type: ignore[method-assign]

    await services.discover.refresh()

    assert peak == 1


async def test_failing_presets_keep_their_old_rows_marked_stale(
    services: Services, provider: FakeMarketData, clock: FakeClock
) -> None:
    await services.discover.refresh()
    provider.screen_fail = TransientProviderError("yahoo", "down")
    clock.now += timedelta(hours=24)

    await services.discover.refresh()

    page = await services.discover.lists()
    for lst in page.lists:
        assert lst.status.state == "stale"
        assert lst.status.reason
        assert lst.rows  # the previous rows survive
    assert page.data_status.state == "stale"


async def test_kept_rows_older_than_a_week_are_dropped(
    services: Services, provider: FakeMarketData, clock: FakeClock
) -> None:
    await services.discover.refresh()
    provider.screen_fail = TransientProviderError("yahoo", "down")
    clock.now += timedelta(days=8)

    await services.discover.refresh()

    page = await services.discover.lists()
    assert all(lst.rows == [] and lst.status.state == "unavailable" for lst in page.lists)


async def test_one_failing_preset_does_not_stop_the_others(
    services: Services, provider: FakeMarketData
) -> None:
    await services.discover.refresh()
    real = provider.screen

    async def only_sg_works(query: ScreenQuery) -> list[ScreenMatch]:
        if query.region == "us":
            raise TransientProviderError("yahoo", "down")
        return await real(query)

    provider.screen = only_sg_works  # type: ignore[method-assign]  # test spy
    provider.screen_hits = {"us": US, "sg": ["AAPL"]}

    await services.discover.refresh()

    page = await services.discover.lists()
    assert [lst.status.state for lst in page.lists] == ["stale", "stale", "ok"]
    assert [r.symbol for r in page.lists[2].rows] == ["AAPL"]  # updated
    assert [r.symbol for r in page.lists[0].rows] == US  # kept


async def test_failing_preset_with_nothing_saved_is_an_empty_unavailable_list(
    services: Services, provider: FakeMarketData
) -> None:
    provider.screen_fail = TransientProviderError("yahoo", "down")

    await services.discover.refresh()

    page = await services.discover.lists()
    assert all(lst.rows == [] and lst.status.state == "unavailable" for lst in page.lists)
    assert page.data_status.state == "unavailable"


async def test_lists_never_calls_the_provider(services: Services, provider: FakeMarketData) -> None:
    await services.discover.refresh()
    before = dict(provider.calls)

    await services.discover.lists()
    await services.discover.lists()

    assert provider.calls == before


async def test_lists_with_nothing_cached_says_it_is_being_prepared(
    services: Services, provider: FakeMarketData
) -> None:
    page = await services.discover.lists()

    assert page.lists == []
    assert page.updated_at is None
    assert page.data_status.state == "unavailable"
    assert page.data_status.reason == EMPTY_REASON
    assert provider.calls["screen"] == 0
    assert await services.discover.needs_startup_build()


async def test_refresh_stores_under_the_discover_key_for_74_hours(
    services: Services, db: Database
) -> None:
    await services.discover.refresh()

    entry = await CacheRepository(db).lookup(CACHE_KEY)

    assert entry is not None
    assert entry.expires_at - entry.created_at == CACHE_TTL == timedelta(hours=74)


async def test_overlapping_refreshes_run_only_one_build(
    services: Services, provider: FakeMarketData
) -> None:
    await asyncio.gather(services.discover.refresh(), services.discover.refresh())

    assert provider.calls["screen"] == 3  # not 6


async def test_a_recent_attempt_blocks_the_startup_build_even_without_a_page(
    services: Services, db: Database
) -> None:
    assert await services.discover.needs_startup_build()
    await services.discover.refresh()
    await db[COLLECTION].delete_one({"key": CACHE_KEY})  # a crash lost the page, not the marker

    assert not await services.discover.needs_startup_build()


# --- freshness follows the weekday schedule -----------------------------------------------------


def _at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)  # 2 Oct 2026 is a Friday


def test_last_scheduled_build_skips_weekends() -> None:
    assert last_scheduled_build(_at(4, 12)) == _at(2, 22, 30)  # Sunday noon -> Friday
    assert last_scheduled_build(_at(5, 1)) == _at(2, 22, 30)  # Monday before the run
    assert last_scheduled_build(_at(5, 22, 30)) == _at(5, 22, 30)


def test_page_built_on_friday_is_not_overdue_all_weekend() -> None:
    built = _at(2, 22, 35)

    assert not is_overdue(built, _at(3, 12))
    assert not is_overdue(built, _at(4, 23, 59))
    assert not is_overdue(built, _at(5, 20))  # Monday daytime: Monday's run has not happened yet


def test_page_missing_this_weeks_run_is_overdue_once_the_grace_has_passed() -> None:
    monday = _at(5, 22, 35)

    assert is_overdue(monday, _at(6, 23, 59))  # Tuesday night, Tuesday's run never landed
    assert not is_overdue(monday, _at(6, 22, 45))  # Tuesday's run is still building
    assert not is_overdue(_at(6, 22, 35), _at(6, 23, 59))


async def test_lists_on_a_sunday_are_not_stale(services: Services, clock: FakeClock) -> None:
    clock.now = _at(2, 22, 35)
    await services.discover.refresh()
    clock.now = _at(4, 12)

    page = await services.discover.lists()

    assert page.data_status.state == "ok"


async def test_lists_missing_tuesdays_run_say_they_are_old(
    services: Services, clock: FakeClock
) -> None:
    clock.now = _at(5, 22, 35)
    await services.discover.refresh()
    clock.now = _at(6, 23, 59)

    page = await services.discover.lists()

    assert page.lists
    assert page.data_status.state == "stale"
