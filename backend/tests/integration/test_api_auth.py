from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.config import Settings
from app.db import Database
from app.main import create_app
from tests.integration.conftest import PASSWORD, ClientFactory, login, register

pytestmark = pytest.mark.integration

COOKIE_DOMAIN = "testserver.local"  # what http.cookiejar assigns to the dotless test host


async def test_register_then_me_returns_the_new_user(client: httpx.AsyncClient) -> None:
    resp = await register(client, "alice@example.com")
    me = await client.get("/api/me")

    assert resp.status_code == 201
    assert resp.json()["user"]["email"] == "alice@example.com"
    assert resp.json()["user"]["role"] == "user"
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"
    assert set(me.json()) == {"id", "email", "role", "created_at"}


async def test_register_sets_cookies_with_expected_attributes(client: httpx.AsyncClient) -> None:
    resp = await register(client, "alice@example.com")

    cookies = {c.split("=")[0]: c.lower() for c in resp.headers.get_list("set-cookie")}
    assert "httponly" in cookies["se_access"]
    assert "path=/api;" in cookies["se_access"] + ";"
    assert "max-age=900" in cookies["se_access"]
    assert "httponly" in cookies["se_refresh"]
    assert "path=/api/auth" in cookies["se_refresh"]
    assert "samesite=lax" in cookies["se_refresh"]


async def test_csrf_endpoint_sets_readable_cookie_matching_body(
    client: httpx.AsyncClient,
) -> None:
    resp = await client.get("/api/auth/csrf")

    assert resp.json()["csrf_token"] == client.cookies.get("se_csrf")
    assert "httponly" not in resp.headers["set-cookie"].lower()
    assert resp.headers["cache-control"] == "no-store"


async def test_register_duplicate_email_returns_409_even_with_different_case(
    new_client: ClientFactory,
) -> None:
    first, second = await new_client(), await new_client()
    await register(first, "alice@example.com")

    resp = await register(second, "ALICE@example.com")

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"


async def test_register_weak_password_returns_422_with_plain_message(
    client: httpx.AsyncClient,
) -> None:
    resp = await register(client, "alice@example.com", "short")

    body = resp.json()["error"]
    assert resp.status_code == 422
    assert body["code"] == "validation_error"
    assert body["message"] == "Password must be at least 12 characters long."
    assert body["details"] and body["details"][0]["message"] == body["message"]


async def test_register_password_equal_to_email_returns_422(client: httpx.AsyncClient) -> None:
    resp = await register(client, "longer.email@example.com", "longer.email@example.com")

    assert resp.status_code == 422
    assert "email" in resp.json()["error"]["message"]


async def test_register_cannot_self_assign_admin_role(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/auth/register",
        json={"email": "mallory@example.com", "password": PASSWORD, "role": "admin"},
    )

    assert resp.status_code == 422


async def test_unsafe_request_without_csrf_header_returns_403(
    client: httpx.AsyncClient,
) -> None:
    del client.headers["X-CSRF-Token"]

    resp = await register(client, "alice@example.com")

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "csrf_failed"


async def test_unsafe_request_with_mismatched_csrf_header_returns_403(
    client: httpx.AsyncClient,
) -> None:
    client.headers["X-CSRF-Token"] = "not-the-cookie-value"

    resp = await login(client, "alice@example.com")

    assert resp.status_code == 403


async def test_login_with_correct_password_sets_session(new_client: ClientFactory) -> None:
    signup, signin = await new_client(), await new_client()
    await register(signup, "alice@example.com")

    resp = await login(signin, "Alice@Example.com")

    assert resp.status_code == 200
    assert (await signin.get("/api/me")).json()["email"] == "alice@example.com"


async def test_login_unknown_email_and_wrong_password_look_identical(
    client: httpx.AsyncClient, new_client: ClientFactory
) -> None:
    await register(await new_client(), "alice@example.com")

    wrong = await login(client, "alice@example.com", "wrong-password-123")
    unknown = await login(client, "nobody@example.com", "wrong-password-123")

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]
    assert wrong.json()["error"]["code"] == unknown.json()["error"]["code"]


async def test_login_locks_account_after_max_failures_then_looks_like_a_wrong_password(
    client: httpx.AsyncClient, new_client: ClientFactory, settings: Settings
) -> None:
    await register(await new_client(), "alice@example.com")
    statuses = [
        (await login(client, "alice@example.com", "wrong-password-123")).status_code
        for _ in range(settings.login_max_failures)
    ]

    locked = await login(client, "alice@example.com", PASSWORD)

    assert statuses == [401] * settings.login_max_failures
    assert locked.status_code == 401
    assert locked.json()["error"]["code"] == "invalid_credentials"


async def test_login_after_lockout_expires_succeeds_and_resets_counter(
    client: httpx.AsyncClient, new_client: ClientFactory, settings: Settings, db: Database
) -> None:
    await register(await new_client(), "alice@example.com")
    for _ in range(settings.login_max_failures):
        await login(client, "alice@example.com", "wrong-password-123")
    yesterday = datetime.now(UTC) - timedelta(days=1)
    await db.users.update_one({}, {"$set": {"locked_until": yesterday}})

    resp = await login(client, "alice@example.com", PASSWORD)

    assert resp.status_code == 200
    doc = await db.users.find_one({"email": "alice@example.com"})
    assert doc is not None
    assert doc["failed_logins"] == 0
    assert doc["locked_until"] is None
    assert doc["last_login_at"] is not None


async def test_login_rate_limit_returns_429_in_error_envelope(client: httpx.AsyncClient) -> None:
    last = None
    for _ in range(11):
        last = await login(client, "nobody@example.com", "wrong-password-123")

    assert last is not None
    assert last.status_code == 429
    assert last.json()["error"]["code"] == "rate_limited"


async def test_refresh_rotates_the_refresh_token(client: httpx.AsyncClient) -> None:
    await register(client, "alice@example.com")
    old = client.cookies.get("se_refresh", path="/api/auth")

    resp = await client.post("/api/auth/refresh")

    assert resp.status_code == 200
    new = client.cookies.get("se_refresh", path="/api/auth")
    assert new
    assert new != old
    assert (await client.get("/api/me")).status_code == 200


async def test_refresh_reusing_an_old_token_revokes_the_whole_family(
    client: httpx.AsyncClient, new_client: ClientFactory
) -> None:
    await register(client, "alice@example.com")
    old = client.cookies.get("se_refresh", path="/api/auth")
    assert old
    await client.post("/api/auth/refresh")
    thief = await new_client()
    thief.cookies.set("se_refresh", old, domain=COOKIE_DOMAIN, path="/api/auth")

    replay = await thief.post("/api/auth/refresh")
    legit = await client.post("/api/auth/refresh")

    assert replay.status_code == 401
    assert legit.status_code == 401  # the family died, including the legitimate newest token


async def test_refresh_without_cookie_returns_401(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/auth/refresh")

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthenticated"


async def test_logout_revokes_refresh_token_and_clears_cookies(
    client: httpx.AsyncClient, new_client: ClientFactory
) -> None:
    await register(client, "alice@example.com")
    refresh_token = client.cookies.get("se_refresh", path="/api/auth")
    assert refresh_token

    resp = await client.post("/api/auth/logout")
    replay = await new_client()
    replay.cookies.set("se_refresh", refresh_token, domain=COOKIE_DOMAIN, path="/api/auth")

    assert resp.status_code == 204
    assert (await client.get("/api/me")).status_code == 401
    assert (await replay.post("/api/auth/refresh")).status_code == 401


async def test_me_without_session_returns_401_envelope(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/me")

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthenticated"


async def test_me_with_garbage_access_cookie_returns_401(client: httpx.AsyncClient) -> None:
    client.cookies.set("se_access", "garbage", domain=COOKIE_DOMAIN, path="/api")

    assert (await client.get("/api/me")).status_code == 401


async def test_refresh_for_disabled_user_returns_401(
    client: httpx.AsyncClient, db: Database
) -> None:
    await register(client, "alice@example.com")
    await db.users.update_one({}, {"$set": {"status": "disabled"}})

    assert (await client.post("/api/auth/refresh")).status_code == 401


async def test_register_issues_a_fresh_csrf_token_in_cookie(client: httpx.AsyncClient) -> None:
    before = client.cookies.get("se_csrf")

    resp = await register(client, "alice@example.com")

    assert resp.cookies.get("se_csrf") not in (None, before)
    assert client.cookies.get("se_csrf") == resp.cookies.get("se_csrf")


async def test_login_rotates_the_csrf_token_and_the_new_one_works(
    client: httpx.AsyncClient, new_client: ClientFactory
) -> None:
    await register(await new_client(), "alice@example.com")
    before = client.cookies.get("se_csrf")

    resp = await login(client, "alice@example.com")

    after = resp.cookies.get("se_csrf")
    assert after not in (None, before)
    assert client.headers["X-CSRF-Token"] == after  # the helper follows rotation like the SPA
    assert (await client.post("/api/auth/logout")).status_code == 204


async def test_login_with_the_pre_login_csrf_token_is_still_accepted_then_replaced(
    client: httpx.AsyncClient, new_client: ClientFactory
) -> None:
    await register(await new_client(), "alice@example.com")
    stale = client.headers["X-CSRF-Token"]

    await login(client, "alice@example.com")
    client.headers["X-CSRF-Token"] = stale

    assert (await client.post("/api/auth/logout")).status_code == 403


async def test_locked_users_existing_session_keeps_working(
    client: httpx.AsyncClient, new_client: ClientFactory, settings: Settings
) -> None:
    await register(client, "alice@example.com")
    attacker = await new_client()
    for _ in range(settings.login_max_failures):
        await login(attacker, "alice@example.com", "wrong-password-123")

    assert (await login(attacker, "alice@example.com")).status_code == 401  # locked out
    assert (await client.get("/api/me")).json()["email"] == "alice@example.com"
    assert (await client.post("/api/auth/refresh")).status_code == 200


@pytest.mark.parametrize(("environment", "expected"), [("prod", 404), ("dev", 200)])
async def test_interactive_docs_and_schema_are_only_served_outside_prod(
    environment: str, expected: int
) -> None:
    settings = Settings.model_validate(
        {"environment": environment, "jwt_secret": "k" * 40, "scheduler_enabled": False}
    )
    app = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as anonymous:
        docs = await anonymous.get("/docs")
        schema = await anonymous.get("/openapi.json")

    assert docs.status_code == schema.status_code == expected


async def test_weak_common_password_is_rejected_at_registration(client: httpx.AsyncClient) -> None:
    resp = await register(client, "alice@example.com", "unbelievable")

    assert resp.status_code == 422
    assert "too common" in resp.json()["error"]["message"]
