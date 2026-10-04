import httpx
import pytest
from fastapi import FastAPI

from tests.integration.conftest import ClientFactory

pytestmark = pytest.mark.integration


async def test_not_found_uses_error_envelope(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/nope")

    body = resp.json()
    assert resp.status_code == 404
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id", "details"}
    assert body["error"]["code"] == "not_found"
    assert body["error"]["request_id"] == resp.headers["x-request-id"]


async def test_valid_incoming_request_id_is_echoed(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/me", headers={"X-Request-ID": "abc-123-DEF"})

    assert resp.headers["x-request-id"] == "abc-123-DEF"
    assert resp.json()["error"]["request_id"] == "abc-123-DEF"


@pytest.mark.parametrize("bad", ["has space", "semi;colon", "x" * 65, "bad_underscore"])
async def test_invalid_incoming_request_id_is_replaced(client: httpx.AsyncClient, bad: str) -> None:
    resp = await client.get("/api/health", headers={"X-Request-ID": bad})

    assert resp.headers["x-request-id"] != bad
    assert len(resp.headers["x-request-id"]) == 32


async def test_responses_carry_security_headers(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/health")

    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "cache-control" not in resp.headers  # no-store is only for /api/auth/*


async def test_validation_error_lists_field_details(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/auth/login", json={"email": "not-an-email", "password": "x"})

    body = resp.json()["error"]
    assert resp.status_code == 422
    assert body["code"] == "validation_error"
    assert body["details"][0]["field"] == "email"


async def test_unhandled_exception_returns_generic_500_without_leaking(
    app: FastAPI, new_client: ClientFactory
) -> None:
    async def boom() -> None:
        raise RuntimeError("super secret internal detail")

    app.add_api_route("/api/test-boom", boom, methods=["GET"])
    client = await new_client()

    resp = await client.get("/api/test-boom", headers={"X-Request-ID": "req-500"})

    body = resp.json()["error"]
    assert resp.status_code == 500
    assert body["code"] == "internal_error"
    assert body["request_id"] == "req-500"
    assert resp.headers["x-request-id"] == "req-500"
    assert "secret" not in resp.text
    assert "Traceback" not in resp.text


async def test_health_reports_database_ok(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "ok"}


async def test_health_returns_200_when_database_is_down(
    app: FastAPI, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing_command(*_args: object, **_kwargs: object) -> None:
        raise ConnectionError("db down")

    monkeypatch.setattr(app.state.db, "command", failing_command)

    resp = await client.get("/api/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "unavailable"}


async def test_cors_allows_configured_origin_with_credentials(
    client: httpx.AsyncClient,
) -> None:
    resp = await client.get("/api/health", headers={"Origin": "http://localhost:5173"})

    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert resp.headers["access-control-allow-credentials"] == "true"


async def test_cors_does_not_allow_unknown_origin(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/health", headers={"Origin": "http://evil.example"})

    assert "access-control-allow-origin" not in resp.headers
