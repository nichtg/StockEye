from collections.abc import AsyncIterator
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

import httpx
import pytest
import respx

from app.config import Settings
from app.providers.alphavantage import AlphaVantageNews
from app.providers.errors import ProviderDataError, ProviderError, RateLimitedError
from app.providers.finnhub import FinnhubNews
from app.providers.google_news import GoogleNewsRss, monthly_windows
from app.providers.marketaux import MarketauxNews
from app.providers.models import NewsQuery
from app.providers.registry import build_news_providers, configured_providers

FIXTURES = Path(__file__).parent / "fixtures"
START = datetime(2026, 9, 1, tzinfo=UTC)
END = datetime(2026, 10, 1, tzinfo=UTC)


def _query(symbol: str = "AAPL", name: str = "Apple Inc.") -> NewsQuery:
    return NewsQuery(symbol=symbol, company_name=name, start=START, end=END)


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(timeout=10) as c:
        yield c


# --- Finnhub ---------------------------------------------------------------------------------


@respx.mock
async def test_finnhub_parses_articles_and_skips_bad_items(client: httpx.AsyncClient) -> None:
    route = respx.get("https://finnhub.io/api/v1/company-news").respond(
        200,
        json=[
            {
                "datetime": 1788000000,
                "headline": "Apple beats",
                "summary": "",
                "source": "Reuters",
                "url": "https://example.com/a",
            },
            {"headline": "no timestamp", "source": "X", "url": "https://example.com/b"},
            {
                "datetime": 1788000100,
                "headline": "bad url",
                "summary": "s",
                "source": "X",
                "url": "not a url",
            },
        ],
    )

    items = await FinnhubNews(client, "KEY").fetch(_query())

    assert [i.title for i in items] == ["Apple beats"]
    assert items[0].summary is None
    assert items[0].provider == "finnhub"
    assert items[0].published_at == datetime.fromtimestamp(1788000000, UTC)
    params = route.calls.last.request.url.params
    assert (params["symbol"], params["from"], params["to"]) == ("AAPL", "2026-09-01", "2026-10-01")


@respx.mock
async def test_finnhub_singapore_symbol_returns_empty_without_calling(
    client: httpx.AsyncClient,
) -> None:
    route = respx.get("https://finnhub.io/api/v1/company-news")

    assert await FinnhubNews(client, "KEY").fetch(_query("D05.SI", "DBS")) == []
    assert not route.called


@respx.mock
async def test_finnhub_non_list_payload_is_data_error(client: httpx.AsyncClient) -> None:
    respx.get("https://finnhub.io/api/v1/company-news").respond(200, json={"error": "x"})

    with pytest.raises(ProviderDataError):
        await FinnhubNews(client, "KEY").fetch(_query())


@respx.mock
async def test_finnhub_401_does_not_leak_key(client: httpx.AsyncClient) -> None:
    respx.get("https://finnhub.io/api/v1/company-news").respond(401)

    with pytest.raises(ProviderError) as info:
        await FinnhubNews(client, "TOPSECRET").fetch(_query())

    assert "credentials rejected" in str(info.value)
    assert "TOPSECRET" not in str(info.value)


@respx.mock
async def test_finnhub_429_carries_retry_after(client: httpx.AsyncClient) -> None:
    respx.get("https://finnhub.io/api/v1/company-news").respond(429, headers={"Retry-After": "12"})

    with pytest.raises(RateLimitedError) as info:
        await FinnhubNews(client, "KEY").fetch(_query())

    assert info.value.retry_after == 12


# --- Marketaux -------------------------------------------------------------------------------


@respx.mock
async def test_marketaux_parses_articles_and_skips_bad_items(client: httpx.AsyncClient) -> None:
    route = respx.get("https://api.marketaux.com/v1/news/all").respond(
        200,
        json={
            "data": [
                {
                    "title": "Apple supplier warns",
                    "description": "Details",
                    "source": "cnbc.com",
                    "url": "https://example.com/m1",
                    "published_at": "2026-09-10T08:30:00.000000Z",
                },
                {"title": "missing fields"},
            ]
        },
    )

    items = await MarketauxNews(client, "KEY").fetch(_query())

    assert len(items) == 1
    assert items[0].published_at == datetime(2026, 9, 10, 8, 30, tzinfo=UTC)
    assert items[0].summary == "Details"
    params = route.calls.last.request.url.params
    assert params["symbols"] == "AAPL"
    assert params["language"] == "en"


@respx.mock
async def test_marketaux_missing_data_key_is_data_error(client: httpx.AsyncClient) -> None:
    respx.get("https://api.marketaux.com/v1/news/all").respond(200, json={"error": {}})

    with pytest.raises(ProviderDataError):
        await MarketauxNews(client, "KEY").fetch(_query())


@respx.mock
async def test_marketaux_malformed_json_is_data_error(client: httpx.AsyncClient) -> None:
    respx.get("https://api.marketaux.com/v1/news/all").respond(200, text="{not json")

    with pytest.raises(ProviderDataError):
        await MarketauxNews(client, "KEY").fetch(_query())


# --- Alpha Vantage ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.parametrize("key", ["Note", "Information"])
async def test_alphavantage_rate_limit_inside_200_body_raises_rate_limited(
    client: httpx.AsyncClient, key: str
) -> None:
    respx.get("https://www.alphavantage.co/query").respond(200, json={key: "25 requests/day"})

    with pytest.raises(RateLimitedError) as info:
        await AlphaVantageNews(client, "KEY").fetch(_query())

    assert info.value.retry_after is None


@respx.mock
async def test_alphavantage_converts_eastern_time_to_utc(client: httpx.AsyncClient) -> None:
    route = respx.get("https://www.alphavantage.co/query").respond(
        200,
        json={
            "feed": [
                {
                    "title": "Summer story",
                    "summary": "s",
                    "source": "Benzinga",
                    "url": "https://example.com/av1",
                    "time_published": "20260910T093000",  # EDT: UTC-4
                },
                {
                    "title": "Winter story",
                    "summary": "s",
                    "source": "Benzinga",
                    "url": "https://example.com/av2",
                    "time_published": "20260115T093000",  # EST: UTC-5
                },
                {
                    "title": "bad date",
                    "source": "X",
                    "url": "https://example.com/av3",
                    "time_published": "yesterday",
                },
            ]
        },
    )

    items = await AlphaVantageNews(client, "KEY").fetch(_query())

    assert [i.published_at for i in items] == [
        datetime(2026, 9, 10, 13, 30, tzinfo=UTC),
        datetime(2026, 1, 15, 14, 30, tzinfo=UTC),
    ]
    params = route.calls.last.request.url.params
    assert params["function"] == "NEWS_SENTIMENT"
    assert params["time_from"] == "20260901T0000"


@respx.mock
async def test_alphavantage_empty_body_without_feed_returns_empty(
    client: httpx.AsyncClient,
) -> None:
    respx.get("https://www.alphavantage.co/query").respond(200, json={"items": "0"})

    assert await AlphaVantageNews(client, "KEY").fetch(_query()) == []


# --- Google News -----------------------------------------------------------------------------


@respx.mock
async def test_google_news_parses_fixture_and_skips_bad_items(client: httpx.AsyncClient) -> None:
    route = respx.get("https://news.google.com/rss/search").respond(
        200, text=(FIXTURES / "google_news.xml").read_text(encoding="utf-8")
    )

    items = await GoogleNewsRss(client).fetch(_query("D05.SI", "DBS Group"))

    assert [i.title for i in items] == [
        "DBS posts record quarterly profit as net interest margin holds",
        "Why analysts - cautiously - upgrade DBS after wealth fee surge",
    ]
    assert [i.source for i in items] == ["The Business Times", "The Straits Times"]
    assert items[0].published_at == datetime(2026, 9, 15, 3, 20, tzinfo=UTC)
    assert items[0].summary is None  # description only repeats the headline
    assert items[1].summary == (
        "Brokerages raised targets after fee income beat expectations & guidance improved."
    )
    assert all(i.provider == "google_news" for i in items)
    params = route.calls.last.request.url.params
    assert params["q"] == '"DBS Group" after:2026-09-01 before:2026-10-01'
    assert (params["hl"], params["gl"], params["ceid"]) == ("en-SG", "SG", "SG:en")


@respx.mock
async def test_google_news_us_symbol_uses_us_edition(client: httpx.AsyncClient) -> None:
    route = respx.get("https://news.google.com/rss/search").respond(
        200, text="<rss version='2.0'><channel></channel></rss>"
    )

    items = await GoogleNewsRss(client).fetch(_query())

    assert items == []
    params = route.calls.last.request.url.params
    assert (params["hl"], params["gl"], params["ceid"]) == ("en-US", "US", "US:en")


def test_monthly_windows_cover_24_contiguous_months_ending_at_end() -> None:
    end = datetime(2026, 10, 31, tzinfo=UTC)

    windows = monthly_windows(end)

    assert len(windows) == 24
    assert windows[-1][1] == end
    assert windows[0][0] == datetime(2024, 10, 31, tzinfo=UTC)
    assert all(a[1] == b[0] for a, b in pairwise(windows))
    assert windows[-1][0] == datetime(2026, 9, 30, tzinfo=UTC)  # day clamped to month length


# --- Registry --------------------------------------------------------------------------------


def test_registry_without_keys_has_only_google_news(client: httpx.AsyncClient) -> None:
    settings = Settings(environment="test")

    assert [p.name for p in build_news_providers(settings, client)] == ["google_news"]
    assert configured_providers(settings) == {
        "yahoo": True,
        "google_news": True,
        "finnhub": False,
        "marketaux": False,
        "alphavantage": False,
    }


def test_registry_with_all_keys_orders_keyed_vendors_before_google(
    client: httpx.AsyncClient,
) -> None:
    settings = Settings.model_validate(
        {
            "environment": "test",
            "finnhub_api_key": "a",
            "marketaux_api_key": "b",
            "alphavantage_api_key": "c",
        }
    )

    names = [p.name for p in build_news_providers(settings, client)]

    assert names == ["finnhub", "marketaux", "alphavantage", "google_news"]
    assert all(configured_providers(settings).values())
