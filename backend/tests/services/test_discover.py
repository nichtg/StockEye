from datetime import timedelta

import pytest

from app.db import Database
from app.providers.errors import TransientProviderError
from app.providers.models import ScreenMatch, ScreenQuery
from app.providers.quota import current_priority
from app.repositories.cache import CacheRepository
from app.services.container import Services
from app.services.discover import CACHE_KEY, EMPTY_REASON, PRESETS
from tests.services.fakes import FakeClock, FakeMarketData

pytestmark = pytest.mark.integration

US = ["AAPL", "MSFT", "ZZZZ"]  # ZZZZ is unknown to the fake vendor: its row is unavailable
SG = ["D05.SI"]


@pytest.fixture(autouse=True)
def _hits(provider: FakeMarketData) -> None:
    provider.screen_hits = {"us": US, "sg": SG}


async def test_refresh_builds_three_lists_and_drops_unavailable_rows(services: Services) -> None:
    await services.discover.refresh()

    page = await services.discover.lists()

    assert [lst.id for lst in page.lists] == [p.id for p in PRESETS]
    assert len(PRESETS) == 3
    for lst in page.lists[:2]:
        assert [r.symbol for r in lst.rows] == ["AAPL", "MSFT"]
        assert lst.status.state == "ok"
    assert [r.symbol for r in page.lists[2].rows] == ["D05.SI"]
    row = page.lists[0].rows[0]
    assert row.country == "United States"
    assert row.sector == "Technology"
    assert row.market_cap == 2.5e9
    assert page.data_status.state == "ok"
    assert page.updated_at is not None


async def test_refresh_makes_its_calls_as_scheduled_work(
    services: Services, provider: FakeMarketData
) -> None:
    seen: list[str] = []
    real = provider.screen

    async def spy(query: ScreenQuery) -> list[ScreenMatch]:
        seen.append(current_priority())
        return await real(query)

    provider.screen = spy  # type: ignore[method-assign]  # test spy

    await services.discover.refresh()

    assert seen == ["scheduled"] * 3


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
    assert [r.symbol for r in page.lists[0].rows] == ["AAPL", "MSFT"]  # kept


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
    assert not await services.discover.has_lists()


async def test_lists_after_the_ttl_still_serve_but_say_they_are_old(
    services: Services, clock: FakeClock
) -> None:
    await services.discover.refresh()
    clock.now += timedelta(hours=30)

    page = await services.discover.lists()

    assert page.lists
    assert page.data_status.state == "stale"


async def test_refresh_stores_under_the_discover_key_for_26_hours(
    services: Services, db: Database
) -> None:
    await services.discover.refresh()

    entry = await CacheRepository(db).lookup(CACHE_KEY)

    assert entry is not None
    assert entry.expires_at - entry.created_at == timedelta(hours=26)
