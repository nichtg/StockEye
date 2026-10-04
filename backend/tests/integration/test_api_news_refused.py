import httpx
import pytest

from app.config import Settings
from app.services.analysis import NEW_SYMBOL_LIMIT_REASON
from tests.integration.conftest import register
from tests.services.fakes import FakeNews

pytestmark = pytest.mark.integration


@pytest.fixture
def settings(settings: Settings) -> Settings:
    settings.max_new_symbols_per_user_per_day = 0  # nothing new is ever admitted
    return settings


async def test_news_endpoint_for_refused_symbol_reports_reason_and_starts_nothing(
    client: httpx.AsyncClient, news_provider: FakeNews
) -> None:
    assert (await register(client, "alice@example.com")).status_code == 201

    resp = await client.get("/api/stocks/AAPL/news")

    body = resp.json()
    assert resp.status_code == 200
    assert body["in_progress"] is False
    assert body["months_done"] == 0
    assert body["status"]["state"] == "unavailable"
    assert body["status"]["reason"] == NEW_SYMBOL_LIMIT_REASON
    assert news_provider.queries == []
