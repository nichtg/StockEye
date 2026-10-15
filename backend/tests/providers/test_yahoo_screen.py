"""YahooMarketData.screen against a faked ``yf.screen``: no network."""

import math
from typing import Any

import pytest
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

from app.providers.errors import RateLimitedError
from app.providers.models import ScreenQuery
from app.providers.yahoo import YahooMarketData


def _query(**overrides: Any) -> ScreenQuery:
    base: dict[str, Any] = {
        "region": "us",
        "min_market_cap": 3e8,
        "max_market_cap": 2e9,
        "min_avg_volume": 200_000,
        "sort_field": "percentchange",
        "sort_asc": False,
        "size": 10,
    }
    return ScreenQuery(**{**base, **overrides})


def _quote(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "symbol": "ABCD",
        "exchange": "NMS",
        "quoteType": "EQUITY",
        "currency": "USD",
        "longName": "Abcd Corp",
        "marketCap": 1.5e9,
        "trailingPE": 11.0,
        "regularMarketPrice": 12.5,
    }
    return {**base, **overrides}


class Capture:
    def __init__(self, quotes: list[dict[str, Any]]) -> None:
        self.quotes = quotes
        self.query: yf.EquityQuery | None = None
        self.kwargs: dict[str, Any] = {}

    def __call__(self, query: yf.EquityQuery, **kwargs: Any) -> dict[str, Any]:
        self.query = query
        self.kwargs = kwargs
        return {"total": len(self.quotes), "quotes": self.quotes}


def _use(monkeypatch: pytest.MonkeyPatch, quotes: list[dict[str, Any]]) -> Capture:
    capture = Capture(quotes)
    monkeypatch.setattr(yf, "screen", capture)
    return capture


def _operands(capture: Capture) -> list[dict[str, Any]]:
    assert capture.query is not None
    return capture.query.to_dict()["operands"]


async def test_screen_builds_the_query_with_region_exchanges_cap_and_volume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _use(monkeypatch, [])

    await YahooMarketData().screen(_query())

    ops = _operands(capture)
    assert {"operator": "EQ", "operands": ["region", "us"]} in ops
    assert {"operator": "BTWN", "operands": ["intradaymarketcap", 3e8, 2e9]} in ops
    assert {"operator": "GT", "operands": ["avgdailyvol3m", 200_000]} in ops
    exchange_op = next(o for o in ops if o["operator"] == "OR")
    codes = {e["operands"][1] for e in exchange_op["operands"]}
    assert {"NMS", "NYQ"} <= codes
    assert "OQB" not in codes
    assert capture.kwargs == {"size": 10, "sortField": "percentchange", "sortAsc": False}
    assert not any(o["operands"][0] == "peratio.lasttwelvemonths" for o in ops)


async def test_screen_pe_limit_also_requires_a_positive_pe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _use(monkeypatch, [])

    await YahooMarketData().screen(_query(max_pe=15.0))

    ops = _operands(capture)
    assert {"operator": "GT", "operands": ["peratio.lasttwelvemonths", 0]} in ops
    assert {"operator": "LT", "operands": ["peratio.lasttwelvemonths", 15.0]} in ops


async def test_screen_singapore_restricts_to_the_sgx_exchange(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _use(monkeypatch, [])

    await YahooMarketData().screen(_query(region="sg"))

    ops = _operands(capture)
    assert {"operator": "EQ", "operands": ["region", "sg"]} in ops
    exchange_op = next(o for o in ops if o["operator"] == "OR")
    assert [e["operands"] for e in exchange_op["operands"]] == [["exchange", "SES"]]


async def test_screen_drops_otc_etf_and_malformed_quotes_and_maps_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use(
        monkeypatch,
        [
            _quote(symbol="GOOD"),
            _quote(symbol="REEMF", exchange="OQB"),
            _quote(symbol="FUND", quoteType="ETF"),
            _quote(symbol="", longName="No symbol"),
            _quote(symbol="NONAME", longName=None, shortName=None),
            _quote(symbol="SHORT", longName=None, shortName="Short Co", marketCap=math.nan),
            _quote(symbol="SGP", exchange="SES", currency="SGD", trailingPE=math.inf),
        ],
    )

    result = await YahooMarketData().screen(_query())

    assert [m.symbol for m in result] == ["GOOD", "SHORT", "SGP"]
    good, short, sgp = result
    assert (good.name, good.exchange, good.currency) == ("Abcd Corp", "US", "USD")
    assert (good.market_cap, good.pe_ratio, good.price) == (1.5e9, 11.0, 12.5)
    assert short.name == "Short Co"
    assert short.market_cap is None
    assert sgp.exchange == "SGX"
    assert sgp.pe_ratio is None


async def test_screen_vendor_rate_limit_maps_to_the_taxonomy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_a: Any, **_k: Any) -> dict[str, Any]:
        raise YFRateLimitError

    monkeypatch.setattr(yf, "screen", boom)

    with pytest.raises(RateLimitedError):
        await YahooMarketData().screen(_query())


def test_screen_query_size_is_capped_at_25() -> None:
    with pytest.raises(ValueError, match="size"):
        _query(size=26)
