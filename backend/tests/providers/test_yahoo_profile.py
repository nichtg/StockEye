"""YahooMarketData.profile against a faked ``Ticker.info``: no network."""

import math
from typing import Any

import pytest
import yfinance as yf

from app.providers.errors import ProviderDataError, SymbolNotFoundError
from app.providers.models import CompanyProfile
from app.providers.yahoo import YahooMarketData


def _use_info(monkeypatch: pytest.MonkeyPatch, info: dict[str, Any]) -> None:
    class FakeTicker:
        def __init__(self, _symbol: str) -> None:
            self.info = info

    monkeypatch.setattr(yf, "Ticker", FakeTicker)


def _info(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"longName": "DBS Group Holdings Ltd", "exchange": "SES"}
    return {**base, **overrides}


async def test_profile_maps_every_field(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_info(
        monkeypatch,
        _info(
            longBusinessSummary="  A bank.  ",
            sector=" Financial Services ",
            industry="Banks - Regional",
            country="Singapore",
            website="https://www.dbs.com",
            fullTimeEmployees=41000,
            marketCap=1.2e11,
            trailingPE=10.5,
            dividendYield=4.28,
            fiftyTwoWeekLow=30.1,
            fiftyTwoWeekHigh=45.6,
            averageVolume=5_000_000,
            currency="SGD",
        ),
    )

    result = await YahooMarketData().profile("D05.SI")

    assert result.description == "A bank."
    assert result.sector == "Financial Services"
    assert result.industry == "Banks - Regional"
    assert result.country == "Singapore"
    assert result.website == "https://www.dbs.com"
    assert result.employees == 41000
    assert result.market_cap == 1.2e11
    assert result.pe_ratio == 10.5
    assert result.week52_low == 30.1
    assert result.week52_high == 45.6
    assert result.avg_volume == 5_000_000
    assert result.currency == "SGD"


async def test_profile_converts_dividend_yield_percent_to_fraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_info(monkeypatch, _info(dividendYield=4.28))

    result = await YahooMarketData().profile("D05.SI")

    assert result.dividend_yield == pytest.approx(0.0428)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://example.com", "http://example.com"),
        ("https://example.com/about?x=1", "https://example.com/about?x=1"),
        ("javascript:alert(1)", None),
        ("JAVASCRIPT:alert(1)", None),
        ("ftp://example.com", None),
        ("/relative/path", None),
        ("www.example.com", None),
        ("https://", None),
        ("", None),
        ("   ", None),
        (12345, None),
    ],
)
async def test_profile_website_keeps_only_absolute_http_urls(
    monkeypatch: pytest.MonkeyPatch, raw: object, expected: str | None
) -> None:
    _use_info(monkeypatch, _info(website=raw))

    result = await YahooMarketData().profile("AAPL")

    assert result.website == expected


async def test_profile_non_finite_and_wrong_typed_values_become_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_info(
        monkeypatch,
        _info(
            marketCap=math.inf,
            trailingPE=math.nan,
            dividendYield=-math.inf,
            fiftyTwoWeekLow="cheap",
            fiftyTwoWeekHigh=None,
            averageVolume=True,
            fullTimeEmployees=math.nan,
            sector=42,
            country="",
        ),
    )

    result = await YahooMarketData().profile("AAPL")

    assert result.market_cap is None
    assert result.pe_ratio is None
    assert result.dividend_yield is None
    assert result.week52_low is None
    assert result.week52_high is None
    assert result.avg_volume is None
    assert result.employees is None
    assert result.sector is None
    assert result.country is None


async def test_profile_short_description_is_kept_whole(monkeypatch: pytest.MonkeyPatch) -> None:
    text = "One. Two."
    _use_info(monkeypatch, _info(longBusinessSummary=text))

    assert (await YahooMarketData().profile("AAPL")).description == text


async def test_profile_long_description_is_cut_at_a_sentence_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentence = "This is a sentence about the business. "
    _use_info(monkeypatch, _info(longBusinessSummary=sentence * 200))  # about 7800 characters

    result = (await YahooMarketData().profile("AAPL")).description

    assert result is not None
    assert len(result) <= 4000
    assert result.endswith("business.")
    assert len(result) > 3900


async def test_profile_long_description_without_sentence_ends_is_cut_hard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_info(monkeypatch, _info(longBusinessSummary="word " * 2000))

    result = (await YahooMarketData().profile("AAPL")).description

    assert result is not None
    assert len(result) <= 4000
    assert len(result) > 3900


async def test_profile_empty_info_is_symbol_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_info(monkeypatch, {"trailingPegRatio": None})

    with pytest.raises(SymbolNotFoundError):
        await YahooMarketData().profile("ZZZZ")


async def test_profile_all_missing_fields_are_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_info(monkeypatch, _info())

    result = await YahooMarketData().profile("AAPL")

    assert result.model_dump() == dict.fromkeys(result.model_dump())


async def test_profile_unsupported_exchange_is_a_data_error_like_quote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_info(monkeypatch, _info(exchange="OQB", symbol="REEMF"))

    with pytest.raises(ProviderDataError):
        await YahooMarketData().profile("REEMF")


async def test_profile_missing_exchange_is_a_data_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_info(monkeypatch, {"longName": "No Exchange Inc."})

    with pytest.raises(ProviderDataError):
        await YahooMarketData().profile("AAPL")


async def test_profile_description_with_sentence_end_exactly_at_the_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = "x" * 3998 + ". " + "tail without end"  # the period is character 4000
    _use_info(monkeypatch, _info(longBusinessSummary=text))

    result = (await YahooMarketData().profile("AAPL")).description

    assert result == "x" * 3998 + "."


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://example.com", "https://example.com"),
        ("HTTPS://Example.com/a", "https://Example.com/a"),
        ("  http://example.com  ", "http://example.com"),
        ("javascript:alert(1)", None),
        ("data:text/html,hi", None),
        ("ftp://example.com", None),
        ("//example.com", None),
        ("example.com", None),
        ("https://", None),
        ("http://[bad", None),
        (None, None),
    ],
)
def test_company_profile_model_keeps_only_absolute_http_websites(
    raw: str | None, expected: str | None
) -> None:
    assert CompanyProfile(website=raw).website == expected
