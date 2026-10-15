"""Discover lists are ranked by their own rule, cut to ten, and keep funds out of US lists."""

from datetime import timedelta

import pytest

from app.db import Database
from app.providers.models import Bar, CompanyProfile
from app.repositories.cache import CacheRepository
from app.services.container import Services
from app.services.discover import CACHE_KEY, PRESETS, ROWS_PER_LIST
from tests.services.fakes import FakeClock, FakeMarketData, make_match, screen_returns

pytestmark = pytest.mark.integration


def _profiles(provider: FakeMarketData, **by_symbol: dict[str, object]) -> None:
    """Override fields of the fake profile for some symbols."""
    real = provider.profile

    async def profile(symbol: str) -> CompanyProfile:
        return (await real(symbol)).model_copy(update=by_symbol.get(symbol, {}))

    provider.profile = profile  # type: ignore[method-assign]  # test double


async def test_movers_list_orders_by_absolute_one_week_move_and_labels_it(
    services: Services, provider: FakeMarketData
) -> None:
    syms = ["AAPL", "MSFT", "NVDA", "GOOG", "AMZN", "META"]
    screen_returns(provider, us=[make_match(s) for s in syms], sg=[])

    await services.discover.refresh()

    movers = (await services.discover.lists()).lists[0]
    values = [r.change_1w_pct for r in movers.rows if r.change_1w_pct is not None]
    assert len(values) == len(movers.rows) == len(syms)
    assert any(c < 0 for c in values) and any(c > 0 for c in values), "fixture must mix signs"
    assert [abs(c) for c in values] == sorted((abs(c) for c in values), reverse=True)
    assert movers.order_label == "Biggest 1-week move first"
    assert movers.description == "Smaller US companies with the biggest moves this week."


async def test_movers_pool_is_screened_by_volume_so_one_week_fallers_can_enter(
    services: Services, provider: FakeMarketData
) -> None:
    movers = next(p for p in PRESETS if p.id == "us_small_movers")
    assert movers.query.sort_field == "dayvolume"  # not today's change, which hides fallers
    screen_returns(provider, us=[make_match("FALL"), *[make_match(s) for s in ("AAPL", "MSFT")]])
    real = provider.bars

    async def crash(symbol: str, *args: object, **kwargs: object) -> list[Bar]:
        bars = await real(symbol, *args, **kwargs)  # type: ignore[arg-type]
        if symbol == "FALL":  # a 50% drop on the last session: a large negative 1-week move
            bars[-1] = bars[-1].model_copy(update={"close": bars[-1].close * 0.5})
        return bars

    provider.bars = crash  # type: ignore[method-assign]  # test double

    await services.discover.refresh()

    top = (await services.discover.lists()).lists[0].rows[0]
    assert top.symbol == "FALL"
    assert top.change_1w_pct is not None and top.change_1w_pct < -30


async def test_value_list_orders_by_lowest_positive_pe_and_drops_rows_without_one(
    services: Services, provider: FakeMarketData
) -> None:
    hits = [
        make_match("AAPL", pe_ratio=9.0),
        make_match("MSFT", pe_ratio=3.5),
        make_match("NVDA", pe_ratio=None),
        make_match("GOOG", pe_ratio=-4.0),  # a loss-maker is not "cheap"
    ]
    screen_returns(provider, us=hits, sg=[])

    await services.discover.refresh()

    value = (await services.discover.lists()).lists[1]
    assert [r.symbol for r in value.rows] == ["MSFT", "AAPL"]
    assert [r.pe_ratio for r in value.rows] == [3.5, 9.0]
    assert value.order_label == "Lowest price-to-earnings first"
    assert value.status.state == "ok"  # unrankable hits are not "lost"


async def test_singapore_list_orders_by_traded_value_and_leaves_out_non_sgd_lines(
    services: Services, provider: FakeMarketData
) -> None:
    hits = [
        make_match("D05.SI", avg_volume_3m=1e6, price=10.0),  # 10m
        make_match("O39.SI", avg_volume_3m=4e6, price=5.0),  # 20m
        make_match("U11.SI", avg_volume_3m=None, price=5.0),  # no volume: dropped
        make_match("Z74.SI", avg_volume_3m=2e6, price=1.0),  # 2m
        make_match("USD.SI", avg_volume_3m=9e9, price=9.0, currency="USD"),  # not comparable
    ]
    screen_returns(provider, us=[], sg=hits)

    await services.discover.refresh()

    sg = (await services.discover.lists()).lists[2]
    assert [r.symbol for r in sg.rows] == ["O39.SI", "D05.SI", "Z74.SI"]
    assert [r.avg_traded_value for r in sg.rows] == [20e6, 10e6, 2e6]
    assert sg.order_label == "Most traded first"


async def test_movers_without_a_one_week_change_sort_last_and_are_never_built_when_full(
    services: Services, provider: FakeMarketData
) -> None:
    hits = [make_match("NEW"), *[make_match(f"S{n}") for n in range(ROWS_PER_LIST)]]
    screen_returns(provider, us=hits, sg=[])
    real = provider.bars

    async def short_history(symbol: str, *args: object, **kwargs: object) -> list[Bar]:
        bars = await real(symbol, *args, **kwargs)  # type: ignore[arg-type]
        return bars[-3:] if symbol == "NEW" else bars  # too short for a 1-week change

    provider.bars = short_history  # type: ignore[method-assign]  # test double

    await services.discover.refresh()

    movers = (await services.discover.lists()).lists[0]
    assert len(movers.rows) == ROWS_PER_LIST
    assert "NEW" not in [r.symbol for r in movers.rows]


async def test_rows_are_built_lazily_only_until_the_list_is_full(
    services: Services, provider: FakeMarketData
) -> None:
    hits = [make_match(f"S{n}", pe_ratio=1.0 + n) for n in range(25)]
    screen_returns(provider, us=hits, sg=[])
    quoted: list[str] = []
    real = provider.quote

    async def spy(symbol: str):  # type: ignore[no-untyped-def]  # test spy
        quoted.append(symbol)
        return await real(symbol)

    provider.quote = spy  # type: ignore[method-assign]

    await services.discover.refresh()

    # Each list builds only its own top 10 (25 candidates exist), never the whole pool.
    assert {f"S{n}" for n in range(ROWS_PER_LIST)} <= set(quoted)
    assert len(set(quoted)) <= 2 * ROWS_PER_LIST


async def test_stale_rule_counts_only_rankable_candidates(
    services: Services, provider: FakeMarketData
) -> None:
    screen_returns(
        provider, us=[make_match(f"S{n}") for n in range(12)] + [make_match("ZZZZ")], sg=[]
    )

    await services.discover.refresh()

    movers = (await services.discover.lists()).lists[0]
    assert len(movers.rows) == ROWS_PER_LIST
    assert movers.status.state == "ok"  # 12 buildable is enough for a list of 10

    screen_returns(
        provider, us=[make_match(f"S{n}") for n in range(5)] + [make_match("ZZZZ")], sg=[]
    )
    await services.discover.refresh()

    movers = (await services.discover.lists()).lists[0]
    assert len(movers.rows) == 5
    assert movers.status.state == "stale"  # one of six candidates was lost


async def test_us_lists_drop_funds_but_keep_banks_reits_and_real_asset_managers(
    services: Services, provider: FakeMarketData
) -> None:
    screen_returns(
        provider,
        us=[
            make_match("AAPL", "Apple Inc."),
            make_match("VCX", "Fundrise Growth Tech Fund, LLC"),
            make_match("GAB", "The Gabelli Equity Trust Inc."),
            make_match("WASH", "Washington Trust Bancorp, Inc."),
            make_match("DHIL", "Diamond Hill Investment Group, Inc."),
            make_match("BDN", "Brandywine Realty Trust"),
        ],
        sg=[
            make_match("A17U.SI", "CapitaLand Ascendas REIT"),
            make_match("C38U.SI", "Mapletree Trust"),
        ],
    )
    _profiles(
        provider,
        VCX={"industry": "Asset Management", "employees": None},
        GAB={"industry": "Asset Management", "employees": None},  # a closed-end fund: no staff
        WASH={"industry": "Banks - Regional", "employees": 600},
        DHIL={"industry": "Asset Management", "employees": 130},
        BDN={"industry": "REIT - Office", "employees": 100},
    )

    await services.discover.refresh()

    page = await services.discover.lists()
    for lst in page.lists[:2]:
        assert sorted(r.symbol for r in lst.rows) == ["AAPL", "BDN", "DHIL", "WASH"]
        assert lst.status.state == "ok"  # funds are not candidates, so their absence is no loss
    assert sorted(r.symbol for r in page.lists[2].rows) == ["A17U.SI", "C38U.SI"]


async def test_asset_manager_with_staff_is_dropped_only_when_its_name_reads_like_a_fund(
    services: Services, provider: FakeMarketData
) -> None:
    screen_returns(
        provider,
        us=[
            make_match("AAPL", "Silvercrest Asset Management Group"),
            make_match("MSFT", "Acme Municipal Income Portfolio"),
        ],
        sg=[],
    )
    _profiles(
        provider,
        AAPL={"industry": "Asset Management", "employees": 200},
        MSFT={"industry": "Asset Management", "employees": 5},
    )

    await services.discover.refresh()

    assert [r.symbol for r in (await services.discover.lists()).lists[0].rows] == ["AAPL"]


async def test_cache_key_is_v2_and_stored_v1_keys_do_not_stop_the_startup_build(
    services: Services, db: Database, clock: FakeClock
) -> None:
    cache = CacheRepository(db)
    await cache.put("discover:v1", {"lists": [], "updated_at": None}, timedelta(hours=1), clock.now)
    await cache.put("discover:attempt", {"at": "x"}, timedelta(hours=6), clock.now)

    assert CACHE_KEY == "discover:v2"
    assert await services.discover.needs_startup_build()  # only old-version keys exist
    assert await services.discover.current_symbols() == set()
