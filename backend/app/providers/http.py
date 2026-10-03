"""HTTP helpers that map httpx failures onto the provider error taxonomy.

Error messages never contain the request URL's query string, so API keys cannot leak into logs
or the admin page. ``redact_url`` is for callers that want to log a URL anyway.
"""

import email.utils
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from app.providers.errors import (
    ProviderDataError,
    ProviderError,
    RateLimitedError,
    TransientProviderError,
)

_SECRET_PARAMS = frozenset({"token", "apikey", "api_token", "api_key"})


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    query = [
        (k, "REDACTED" if k.lower() in _SECRET_PARAMS else v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit(parts._replace(query=urlencode(query)))


def parse_retry_after(value: str | None, now: datetime | None = None) -> float | None:
    """Seconds to wait, from a ``Retry-After`` header in delta-seconds or HTTP-date form."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - (now or datetime.now(UTC))).total_seconds())


async def _get(
    client: httpx.AsyncClient, url: str, *, provider: str, params: dict[str, Any] | None
) -> httpx.Response:
    try:
        response = await client.get(url, params=params)
    except httpx.TimeoutException as exc:
        raise TransientProviderError(provider, "request timed out") from exc
    except httpx.TransportError as exc:
        raise TransientProviderError(provider, f"network error ({type(exc).__name__})") from exc
    status = response.status_code
    if status == httpx.codes.TOO_MANY_REQUESTS:
        raise RateLimitedError(provider, parse_retry_after(response.headers.get("Retry-After")))
    if status >= httpx.codes.INTERNAL_SERVER_ERROR:
        raise TransientProviderError(provider, f"server error {status}")
    if status in (401, 403):
        raise ProviderError(provider, f"credentials rejected (HTTP {status})")
    if status >= httpx.codes.BAD_REQUEST:
        raise ProviderDataError(provider, f"unexpected HTTP {status}")
    return response


async def get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    provider: str,
    params: dict[str, Any] | None = None,
) -> object:
    response = await _get(client, url, provider=provider, params=params)
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderDataError(provider, "response was not valid JSON") from exc


async def get_text(
    client: httpx.AsyncClient,
    url: str,
    *,
    provider: str,
    params: dict[str, Any] | None = None,
) -> str:
    response = await _get(client, url, provider=provider, params=params)
    return response.text
