from types import SimpleNamespace

import httpx
import pytest
from fastapi import Request

from app.api.limits import MACRO, OVERVIEW, SEARCH, STOCK, user_or_ip_key
from app.auth.tokens import create_access_token
from app.config import Settings
from tests.integration.conftest import ClientFactory, register

pytestmark = pytest.mark.integration


@pytest.fixture
def settings(settings: Settings) -> Settings:
    settings.rate_limits = {
        SEARCH: "2/minute",
        STOCK: "3/minute",
        MACRO: "1/minute",
        OVERVIEW: "1/minute",
    }
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


def _request(settings: Settings, cookie: str | None, client_host: str = "10.0.0.7") -> Request:
    headers = [(b"cookie", f"se_access={cookie}".encode())] if cookie else []

    app = SimpleNamespace(state=SimpleNamespace(settings=settings))
    scope = {
        "type": "http",
        "headers": headers,
        "client": (client_host, 1234),
        "app": app,
    }
    return Request(scope)


def test_user_or_ip_key_uses_the_user_id_from_a_valid_access_cookie(settings: Settings) -> None:
    token = create_access_token("64b7f0c2a1b2c3d4e5f60718", settings)

    assert user_or_ip_key(_request(settings, token)) == "user:64b7f0c2a1b2c3d4e5f60718"


def test_user_or_ip_key_falls_back_to_the_address_without_a_usable_cookie(
    settings: Settings,
) -> None:
    assert user_or_ip_key(_request(settings, None)) == "ip:10.0.0.7"
    assert user_or_ip_key(_request(settings, "forged.token.value")) == "ip:10.0.0.7"
