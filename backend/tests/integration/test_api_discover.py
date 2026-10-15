import httpx
import pytest
from fastapi import FastAPI

from app.services.container import Services
from tests.integration.conftest import register
from tests.services.fakes import FakeMarketData
from tests.services.test_discover import give_hits_traded_volume

pytestmark = pytest.mark.integration


@pytest.fixture
async def user(client: httpx.AsyncClient) -> httpx.AsyncClient:
    assert (await register(client, "alice@example.com")).status_code == 201
    return client


async def test_discover_without_session_returns_401(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/discover")).status_code == 401


async def test_discover_before_the_first_build_is_empty_and_unavailable(
    user: httpx.AsyncClient, provider: FakeMarketData
) -> None:
    resp = await user.get("/api/discover")

    body = resp.json()
    assert resp.status_code == 200
    assert body["lists"] == []
    assert body["updated_at"] is None
    assert body["data_status"]["state"] == "unavailable"
    assert provider.calls["screen"] == 0


async def test_discover_returns_the_stored_lists(
    user: httpx.AsyncClient, app: FastAPI, provider: FakeMarketData
) -> None:
    provider.screen_hits = {"us": ["AAPL"], "sg": ["D05.SI"]}
    give_hits_traded_volume(provider)
    services: Services = app.state.services
    await services.discover.refresh()
    screens = provider.calls["screen"]

    resp = await user.get("/api/discover")

    body = resp.json()
    assert resp.status_code == 200
    assert set(body) == {"lists", "updated_at", "data_status"}
    assert [lst["id"] for lst in body["lists"]] == [
        "us_small_movers",
        "us_value_small",
        "sg_under_radar",
    ]
    first = body["lists"][0]
    assert set(first) == {"id", "title", "description", "order_label", "rows", "status"}
    row = first["rows"][0]
    assert row["symbol"] == "AAPL"
    assert {"country", "sector", "market_cap", "pe_ratio", "avg_traded_value"} <= set(row)
    assert first["order_label"] == "Biggest 1-week move first"
    assert body["data_status"]["state"] == "ok"
    assert provider.calls["screen"] == screens  # reading never screens again
