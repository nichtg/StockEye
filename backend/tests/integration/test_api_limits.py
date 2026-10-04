import httpx
import pytest
from limits import parse

from app.config import RateLimits, Settings
from tests.integration.conftest import ClientFactory, register

pytestmark = pytest.mark.integration


@pytest.fixture
def settings(settings: Settings) -> Settings:
    settings.rate_limits = RateLimits(
        search=parse("2/minute"),
        stock=parse("3/minute"),
        macro=parse("1/minute"),
        overview=parse("1/minute"),
        watchlist=parse("2/minute"),
    )
    return settings


@pytest.fixture
async def alice(client: httpx.AsyncClient) -> httpx.AsyncClient:
    assert (await register(client, "alice@example.com")).status_code == 201
    return client


async def test_search_past_the_budget_returns_429_envelope(alice: httpx.AsyncClient) -> None:
    statuses = [(await alice.get("/api/stocks/search?q=app")).status_code for _ in range(3)]

    assert statuses == [200, 200, 429]
    body = (await alice.get("/api/stocks/search?q=app")).json()
    assert body["error"]["code"] == "rate_limited"


async def test_quote_chart_and_technical_draw_on_one_budget(alice: httpx.AsyncClient) -> None:
    paths = ["/api/stocks/AAPL", "/api/stocks/AAPL/chart", "/api/stocks/AAPL/technical"]
    first_three = [(await alice.get(p)).status_code for p in paths]

    fourth = await alice.get("/api/stocks/AAPL")

    assert first_three == [200, 200, 200]
    assert fourth.status_code == 429


async def test_macro_and_overview_have_their_own_budgets(alice: httpx.AsyncClient) -> None:
    macro = [(await alice.get("/api/stocks/AAPL/macro")).status_code for _ in range(2)]
    overview = [(await alice.get("/api/watchlist/overview")).status_code for _ in range(2)]

    assert macro == [200, 429]
    assert overview == [200, 429]


async def test_budget_is_per_user_not_per_address(
    alice: httpx.AsyncClient, new_client: ClientFactory
) -> None:
    for _ in range(3):
        await alice.get("/api/stocks/search?q=app")
    bob = await new_client()  # same test address, different account
    assert (await register(bob, "bob@example.com")).status_code == 201

    assert (await alice.get("/api/stocks/search?q=app")).status_code == 429
    assert (await bob.get("/api/stocks/search?q=app")).status_code == 200


async def test_watchlist_writes_share_one_budget(alice: httpx.AsyncClient) -> None:
    statuses = [
        (await alice.put("/api/watchlist/AAPL")).status_code,
        (await alice.delete("/api/watchlist/AAPL")).status_code,
        (await alice.put("/api/watchlist/AAPL")).status_code,
    ]

    assert statuses == [200, 200, 429]


def test_rate_limits_reject_an_unparsable_rate_string() -> None:
    with pytest.raises(ValueError, match="macro"):
        RateLimits(macro="often")  # type: ignore[arg-type]  # the point of the test
