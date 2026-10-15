"""Discover lists are ranked by their own rule, cut to ten, and keep funds out of US lists."""

from datetime import timedelta

import pytest

from app.db import Database
from app.providers.models import Bar, CompanyProfile
from app.repositories.cache import CacheRepository
from app.services.container import Services
from app.services.discover import CACHE_KEY, ROWS_PER_LIST
from tests.services.fakes import FakeClock, FakeMarketData
from tests.services.test_discover import _match, _screen_returns

pytestmark = pytest.mark.integration


async def test_movers_list_orders_by_absolute_one_week_move_and_labels_it(
    services: Services, provider: FakeMarketData
) -> None:
    syms = ["AAPL", "MSFT", "NVDA", "GOOG", "AMZN", "META"]
    _screen_returns(provider, us=[_match(s) for s in syms], sg=[])

    await services.discover.refresh()

    movers = (await services.discover.lists()).lists[0]
    changes = [r.change_1w_pct for r in movers.rows]
    assert all(c is not None for c in changes)
    values = [c for c in changes if c is not None]
    assert any(c < 0 for c in values) and any(c > 0 for c in values), "fixture must mix signs"
    assert [abs(c) for c in values] == sorted((abs(c) for c in values), reverse=True)
    assert movers.order_label == "Biggest 1-week move first"
    assert movers.description == "Smaller US companies with the biggest moves this week."


async def test_value_list_orders_by_lowest_positive_pe_and_drops_rows_without_one(
    services: Services, provider: FakeMarketData
) -> None:
    hits = [
        _match("AAPL", pe_ratio=9.0),
        _match("MSFT", pe_ratio=3.5),
        _match("NVDA", pe_ratio=None),  # the fake profile's P/E (21.5) is the fallback
        _match("GOOG", pe_ratio=-4.0),  # a loss-maker is not "cheap"
    ]
    _screen_returns(provider, us=hits, sg=[])

    await services.discover.refresh()

    value = (await services.discover.lists()).lists[1]
    assert [r.symbol for r in value.rows] == ["MSFT", "AAPL", "NVDA"]
    assert [r.pe_ratio for r in value.rows] == [3.5, 9.0, 21.5]
    assert value.order_label == "Lowest price-to-earnings first"


async def test_value_list_drops_rows_with_no_pe_anywhere(
    services: Services, provider: FakeMarketData
) -> None:
    _screen_returns(provider, us=[_match("AAPL", pe_ratio=None), _match("MSFT")], sg=[])
    real = provider.profile

    async def no_pe(symbol: str) -> CompanyProfile:
        return (await real(symbol)).model_copy(update={"pe_ratio": None})

    provider.profile = no_pe  # type: ignore[method-assign]  # test double

    await services.discover.refresh()

    value = (await services.discover.lists()).lists[1]
    assert [r.symbol for r in value.rows] == ["MSFT"]


async def test_singapore_list_orders_by_average_daily_traded_value(
    services: Services, provider: FakeMarketData
) -> None:
    hits = [
        _match("D05.SI", avg_volume_3m=1e6, price=10.0),  # 10m
        _match("O39.SI", avg_volume_3m=4e6, price=5.0),  # 20m
        _match("U11.SI", avg_volume_3m=None, price=5.0),  # no volume: dropped
        _match("Z74.SI", avg_volume_3m=2e6, price=1.0),  # 2m
    ]
    _screen_returns(provider, us=[], sg=hits)

    await services.discover.refresh()

    sg = (await services.discover.lists()).lists[2]
    assert [r.symbol for r in sg.rows] == ["O39.SI", "D05.SI", "Z74.SI"]
    assert [r.avg_traded_value for r in sg.rows] == [20e6, 10e6, 2e6]
    assert sg.order_label == "Most traded first"


async def test_movers_without_a_one_week_change_go_last_and_are_cut_first(
    services: Services, provider: FakeMarketData
) -> None:
    hits = [_match("NEW"), *[_match(f"S{n}") for n in range(ROWS_PER_LIST)]]
    _screen_returns(provider, us=hits, sg=[])
    real = provider.bars

    async def short_history(symbol: str, *args: object, **kwargs: object) -> list[Bar]:
        bars = await real(symbol, *args, **kwargs)  # type: ignore[arg-type]
        return bars[-3:] if symbol == "NEW" else bars  # too short for a 1-week change

    provider.bars = short_history  # type: ignore[method-assign]  # test double

    await services.discover.refresh()

    movers = (await services.discover.lists()).lists[0]
    assert len(movers.rows) == ROWS_PER_LIST
    assert "NEW" not in [r.symbol for r in movers.rows]


async def test_stale_rule_counts_only_buildable_candidates(
    services: Services, provider: FakeMarketData
) -> None:
    _screen_returns(provider, us=[_match(f"S{n}") for n in range(12)] + [_match("ZZZZ")], sg=[])

    await services.discover.refresh()

    movers = (await services.discover.lists()).lists[0]
    assert len(movers.rows) == ROWS_PER_LIST
    assert movers.status.state == "ok"  # 12 built is enough for a list of 10

    _screen_returns(provider, us=[_match(f"S{n}") for n in range(5)] + [_match("ZZZZ")], sg=[])
    await services.discover.refresh()

    movers = (await services.discover.lists()).lists[0]
    assert len(movers.rows) == 5
    assert movers.status.state == "stale"  # one of six candidates was lost


async def test_us_lists_drop_funds_by_name_but_singapore_keeps_trusts(
    services: Services, provider: FakeMarketData
) -> None:
    _screen_returns(
        provider,
        us=[
            _match("AAPL", "Apple Inc."),
            _match("GAB", "The Gabelli Equity Trust Inc."),
            _match("VCX", "Fundrise Growth Tech Fund, LLC"),
            _match("NVDA", "Trustco Bank Corp"),  # "Trustco" is not the word "trust"
        ],
        sg=[_match("A17U.SI", "CapitaLand Ascendas REIT"), _match("C38U.SI", "Mapletree Trust")],
    )

    await services.discover.refresh()

    page = await services.discover.lists()
    for lst in page.lists[:2]:
        assert sorted(r.symbol for r in lst.rows) == ["AAPL", "NVDA"]
        assert lst.status.state == "ok"  # funds are not candidates, so their absence is no loss
    assert sorted(r.symbol for r in page.lists[2].rows) == ["A17U.SI", "C38U.SI"]


async def test_us_lists_drop_asset_management_profiles_that_the_name_rule_misses(
    services: Services, provider: FakeMarketData
) -> None:
    _screen_returns(provider, us=[_match("AAPL"), _match("VCX", "Fundrise Growth Tech")], sg=[])
    real = provider.profile

    async def profile(symbol: str) -> CompanyProfile:
        found = await real(symbol)
        if symbol == "VCX":
            return found.model_copy(update={"industry": "Asset Management"})
        return found

    provider.profile = profile  # type: ignore[method-assign]  # test double

    await services.discover.refresh()

    page = await services.discover.lists()
    assert [r.symbol for r in page.lists[0].rows] == ["AAPL"]
    assert page.lists[0].status.state == "ok"


async def test_cache_key_is_v2_and_stored_v1_keys_do_not_stop_the_startup_build(
    services: Services, db: Database, clock: FakeClock
) -> None:
    cache = CacheRepository(db)
    await cache.put("discover:v1", {"lists": [], "updated_at": None}, timedelta(hours=1), clock.now)
    await cache.put("discover:attempt", {"at": "x"}, timedelta(hours=6), clock.now)

    assert CACHE_KEY == "discover:v2"
    assert await services.discover.needs_startup_build()  # only old-version keys exist
    assert await services.discover.current_symbols() == set()
