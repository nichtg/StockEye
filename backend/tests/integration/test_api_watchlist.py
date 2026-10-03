import httpx
import pytest
from limits import parse

from app.config import RateLimits, Settings
from tests.integration.conftest import ClientFactory, register
from tests.services.fakes import FakeMarketData

pytestmark = pytest.mark.integration


@pytest.fixture
def settings(settings: Settings) -> Settings:
    settings.rate_limits = RateLimits(
        watchlist=parse("1000/minute")
    )  # the cap test makes 50+ writes
    return settings


async def test_watchlist_requires_authentication(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/watchlist")).status_code == 401


async def test_watchlist_new_user_starts_empty(client: httpx.AsyncClient) -> None:
    await register(client, "alice@example.com")

    resp = await client.get("/api/watchlist")

    assert resp.json() == {"symbols": []}


async def test_watchlist_add_uppercases_and_is_idempotent(client: httpx.AsyncClient) -> None:
    await register(client, "alice@example.com")

    await client.put("/api/watchlist/aapl")
    resp = await client.put("/api/watchlist/AAPL")

    assert resp.status_code == 200
    assert resp.json() == {"symbols": ["AAPL"]}


async def test_watchlist_add_accepts_sgx_style_symbols(client: httpx.AsyncClient) -> None:
    await register(client, "alice@example.com")

    resp = await client.put("/api/watchlist/D05.SI")

    assert resp.json() == {"symbols": ["D05.SI"]}


async def test_watchlist_remove_is_idempotent(client: httpx.AsyncClient) -> None:
    await register(client, "alice@example.com")
    await client.put("/api/watchlist/AAPL")
    await client.put("/api/watchlist/MSFT")

    first = await client.delete("/api/watchlist/AAPL")
    second = await client.delete("/api/watchlist/AAPL")

    assert first.status_code == second.status_code == 200
    assert second.json() == {"symbols": ["MSFT"]}


async def test_watchlist_remove_without_existing_list_is_ok(client: httpx.AsyncClient) -> None:
    await register(client, "alice@example.com")

    resp = await client.delete("/api/watchlist/AAPL")

    assert resp.status_code == 200
    assert resp.json() == {"symbols": []}


@pytest.mark.parametrize("symbol", ["-AAPL", ".X", "A" * 16, "AA PL", "AAPL%24"])
async def test_watchlist_invalid_symbol_returns_422(client: httpx.AsyncClient, symbol: str) -> None:
    await register(client, "alice@example.com")

    resp = await client.put(f"/api/watchlist/{symbol}")

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


async def test_watchlist_symbol_of_max_length_is_accepted(client: httpx.AsyncClient) -> None:
    await register(client, "alice@example.com")

    resp = await client.put("/api/watchlist/" + "A" * 15)

    assert resp.status_code == 200


async def test_watchlist_cap_returns_409_but_existing_symbols_still_idempotent(
    client: httpx.AsyncClient,
) -> None:
    await register(client, "alice@example.com")
    for i in range(50):
        assert (await client.put(f"/api/watchlist/S{i}")).status_code == 200

    over = await client.put("/api/watchlist/EXTRA")
    again = await client.put("/api/watchlist/S0")
    listed = await client.get("/api/watchlist")

    assert over.status_code == 409
    assert over.json()["error"]["code"] == "conflict"
    assert again.status_code == 200
    assert len(listed.json()["symbols"]) == 50
    assert "EXTRA" not in listed.json()["symbols"]


async def test_watchlist_is_private_per_user(new_client: ClientFactory) -> None:
    alice, bob = await new_client(), await new_client()
    await register(alice, "alice@example.com")
    await register(bob, "bob@example.com")

    await alice.put("/api/watchlist/AAPL")

    assert (await bob.get("/api/watchlist")).json() == {"symbols": []}


async def test_watchlist_add_unknown_symbol_returns_404_and_saves_nothing(
    client: httpx.AsyncClient,
) -> None:
    await register(client, "alice@example.com")

    resp = await client.put("/api/watchlist/ZZZZ")

    assert resp.status_code == 404
    assert resp.json()["error"]["message"] == "We couldn't find that stock."
    assert (await client.get("/api/watchlist")).json() == {"symbols": []}


async def test_watchlist_add_repeated_unknown_symbol_costs_no_vendor_call(
    client: httpx.AsyncClient, provider: FakeMarketData
) -> None:
    await register(client, "alice@example.com")

    for _ in range(3):
        assert (await client.put("/api/watchlist/ZZZZ")).status_code == 404

    assert provider.calls["quote"] == 1  # the not-found answer is remembered for 6 hours


async def test_watchlist_add_known_symbol_resolves_it_cache_first(
    client: httpx.AsyncClient, provider: FakeMarketData
) -> None:
    await register(client, "alice@example.com")

    await client.put("/api/watchlist/AAPL")
    await client.put("/api/watchlist/AAPL")

    assert provider.calls["quote"] == 1
