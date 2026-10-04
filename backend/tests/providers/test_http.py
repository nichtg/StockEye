from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.providers.errors import (
    ProviderDataError,
    ProviderError,
    RateLimitedError,
    TransientProviderError,
)
from app.providers.http import get_json, get_text, parse_retry_after, redact_url

URL = "https://api.example.com/v1/thing"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(timeout=10) as c:
        yield c


@respx.mock
async def test_get_json_success_returns_parsed_body(client: httpx.AsyncClient) -> None:
    respx.get(URL).respond(200, json={"a": 1})

    assert await get_json(client, URL, provider="p", params={"x": "1"}) == {"a": 1}


@respx.mock
async def test_get_json_429_with_seconds_retry_after(client: httpx.AsyncClient) -> None:
    respx.get(URL).respond(429, headers={"Retry-After": "7"})

    with pytest.raises(RateLimitedError) as info:
        await get_json(client, URL, provider="p")

    assert info.value.retry_after == 7.0


@respx.mock
async def test_get_json_429_without_retry_after_has_none(client: httpx.AsyncClient) -> None:
    respx.get(URL).respond(429)

    with pytest.raises(RateLimitedError) as info:
        await get_json(client, URL, provider="p")

    assert info.value.retry_after is None


def test_parse_retry_after_http_date() -> None:
    now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

    assert parse_retry_after("Thu, 01 Jan 2026 00:00:30 GMT", now) == 30.0


def test_parse_retry_after_garbage_is_none() -> None:
    assert parse_retry_after("soon") is None


@respx.mock
async def test_get_json_503_raises_transient(client: httpx.AsyncClient) -> None:
    respx.get(URL).respond(503)

    with pytest.raises(TransientProviderError):
        await get_json(client, URL, provider="p")


@respx.mock
async def test_get_json_timeout_raises_transient(client: httpx.AsyncClient) -> None:
    respx.get(URL).mock(side_effect=httpx.ConnectTimeout("slow"))

    with pytest.raises(TransientProviderError):
        await get_json(client, URL, provider="p")


@respx.mock
async def test_get_json_connect_error_raises_transient(client: httpx.AsyncClient) -> None:
    respx.get(URL).mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(TransientProviderError):
        await get_json(client, URL, provider="p")


@respx.mock
@pytest.mark.parametrize("status", [401, 403])
async def test_get_json_auth_failure_hides_the_api_key(
    client: httpx.AsyncClient, status: int
) -> None:
    respx.get(URL).respond(status)

    with pytest.raises(ProviderError) as info:
        await get_json(client, URL, provider="p", params={"apikey": "SECRET123"})

    assert "credentials rejected" in str(info.value)
    assert "SECRET123" not in str(info.value)
    assert not isinstance(info.value, TransientProviderError)


@respx.mock
async def test_get_json_other_4xx_is_data_error(client: httpx.AsyncClient) -> None:
    respx.get(URL).respond(404)

    with pytest.raises(ProviderDataError):
        await get_json(client, URL, provider="p")


@respx.mock
async def test_get_json_malformed_body_is_data_error(client: httpx.AsyncClient) -> None:
    respx.get(URL).respond(200, text="<html>oops")

    with pytest.raises(ProviderDataError):
        await get_json(client, URL, provider="p")


@respx.mock
async def test_get_text_returns_body(client: httpx.AsyncClient) -> None:
    respx.get(URL).respond(200, text="hello")

    assert await get_text(client, URL, provider="p") == "hello"


def test_redact_url_masks_secret_params_only() -> None:
    url = "https://x.test/q?symbol=AAPL&token=abc&apikey=def&api_token=ghi"

    redacted = redact_url(url)

    assert "symbol=AAPL" in redacted
    assert "abc" not in redacted
    assert "def" not in redacted
    assert "ghi" not in redacted
