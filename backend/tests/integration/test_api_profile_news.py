from datetime import timedelta

import httpx
import pytest

from app.db import Database
from app.providers.errors import RateLimitedError
from tests.integration.conftest import register
from tests.services.fakes import CLOSED_NOW, FakeMarketData
from tests.services.test_news_feed import seed

pytestmark = pytest.mark.integration


@pytest.fixture
async def user(client: httpx.AsyncClient) -> httpx.AsyncClient:
    assert (await register(client, "alice@example.com")).status_code == 201
    return client


async def test_profile_and_news_articles_without_session_return_401(
    client: httpx.AsyncClient,
) -> None:
    for path in ("/api/stocks/AAPL/profile", "/api/stocks/AAPL/news/articles"):
        assert (await client.get(path)).status_code == 401


async def test_profile_returns_fields_and_data_status(user: httpx.AsyncClient) -> None:
    resp = await user.get("/api/stocks/D05.SI/profile")

    body = resp.json()
    assert resp.status_code == 200
    assert set(body) == {
        "description",
        "sector",
        "industry",
        "country",
        "website",
        "employees",
        "market_cap",
        "pe_ratio",
        "dividend_yield",
        "week52_low",
        "week52_high",
        "avg_volume",
        "currency",
        "data_status",
    }
    assert body["currency"] == "SGD"
    assert body["dividend_yield"] == pytest.approx(0.0428)
    assert body["data_status"]["state"] == "ok"


async def test_profile_unknown_symbol_returns_404(user: httpx.AsyncClient) -> None:
    resp = await user.get("/api/stocks/ZZZZ/profile")

    assert resp.status_code == 404


async def test_profile_provider_down_with_nothing_saved_returns_503(
    user: httpx.AsyncClient, provider: FakeMarketData
) -> None:
    provider.fail_with = RateLimitedError("yahoo")

    assert (await user.get("/api/stocks/AAPL/profile")).status_code == 503


async def test_news_articles_returns_page_shape(user: httpx.AsyncClient, db: Database) -> None:
    for i in range(3):
        await seed(
            db, "AAPL", f"headline {i}", CLOSED_NOW - timedelta(hours=i + 1), 0.5 if i else None
        )

    resp = await user.get("/api/stocks/AAPL/news/articles", params={"limit": 2})
    rest = await user.get(
        "/api/stocks/AAPL/news/articles", params={"limit": 2, "before": resp.json()["next_cursor"]}
    )

    body = resp.json()
    assert resp.status_code == 200
    assert set(body) == {"articles", "next_cursor", "since", "status"}
    assert [a["title"] for a in body["articles"]] == ["headline 0", "headline 1"]
    assert set(body["articles"][0]) == {
        "published_at",
        "title",
        "url",
        "source",
        "sentiment_label",
        "sentiment",
    }
    assert body["articles"][0]["sentiment_label"] == "not_scored"
    assert body["articles"][1]["sentiment_label"] == "positive"
    assert [a["title"] for a in rest.json()["articles"]] == ["headline 2"]
    assert rest.json()["next_cursor"] is None


async def test_news_articles_validates_limit_and_cursor(user: httpx.AsyncClient) -> None:
    for limit in (0, 51, -1, "x"):
        resp = await user.get("/api/stocks/AAPL/news/articles", params={"limit": limit})
        assert resp.status_code == 422, limit
    for limit in (1, 50):
        ok = await user.get("/api/stocks/AAPL/news/articles", params={"limit": limit})
        assert ok.status_code == 200, limit

    bad = await user.get("/api/stocks/AAPL/news/articles", params={"before": "garbage"})

    assert bad.status_code == 422


async def test_news_articles_limit_max_returns_up_to_fifty(
    user: httpx.AsyncClient, db: Database
) -> None:
    for i in range(55):
        await seed(db, "AAPL", f"headline {i}", CLOSED_NOW - timedelta(minutes=i + 1))

    resp = await user.get("/api/stocks/AAPL/news/articles", params={"limit": 50})
    default = await user.get("/api/stocks/AAPL/news/articles")

    assert len(resp.json()["articles"]) == 50
    assert resp.json()["next_cursor"] is not None
    assert len(default.json()["articles"]) == 30
