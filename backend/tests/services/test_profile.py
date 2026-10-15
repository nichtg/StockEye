from datetime import timedelta

import pytest

from app.providers.errors import RateLimitedError
from app.services.container import Services
from app.services.errors import AppError
from tests.services.fakes import CLOSED_NOW, FakeClock, FakeMarketData

pytestmark = pytest.mark.integration


async def test_profile_second_call_is_served_from_cache(
    services: Services, provider: FakeMarketData
) -> None:
    first, status = await services.market.profile("AAPL")
    second, _ = await services.market.profile("AAPL")

    assert second == first
    assert status.state == "ok"
    assert provider.calls["profile"] == 1


async def test_profile_refetches_after_the_24_hour_ttl(
    services: Services, clock: FakeClock, provider: FakeMarketData
) -> None:
    await services.market.profile("AAPL")
    clock.now = CLOSED_NOW + timedelta(hours=23)
    await services.market.profile("AAPL")
    assert provider.calls["profile"] == 1

    clock.now = CLOSED_NOW + timedelta(hours=25)
    await services.market.profile("AAPL")

    assert provider.calls["profile"] == 2


async def test_profile_serves_stale_copy_when_provider_fails_after_ttl(
    services: Services, clock: FakeClock, provider: FakeMarketData
) -> None:
    saved, _ = await services.market.profile("AAPL")
    clock.now = CLOSED_NOW + timedelta(hours=30)
    provider.fail_with = RateLimitedError("yahoo")

    profile, status = await services.market.profile("AAPL")

    assert profile == saved
    assert status.state == "stale"


async def test_profile_with_nothing_saved_and_provider_down_is_503(
    services: Services, provider: FakeMarketData
) -> None:
    provider.fail_with = RateLimitedError("yahoo")

    with pytest.raises(AppError) as caught:
        await services.market.profile("AAPL")

    assert caught.value.status == 503


async def test_profile_unknown_symbol_is_404_and_remembered(
    services: Services, provider: FakeMarketData
) -> None:
    for _ in range(2):
        with pytest.raises(AppError) as caught:
            await services.market.profile("ZZZZ")
        assert caught.value.status == 404

    assert provider.calls["profile"] == 1
