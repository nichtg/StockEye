from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.auth.tokens import create_access_token
from app.config import Settings
from app.db import Database
from app.main import create_app
from tests.integration.conftest import PASSWORD, ClientFactory, bearer, login, register

pytestmark = pytest.mark.integration


async def _refresh(client: httpx.AsyncClient, token: str | None) -> httpx.Response:
    body = {} if token is None else {"refresh_token": token}
    return await client.post("/api/auth/refresh", json=body)


async def test_register_then_me_returns_the_new_user(client: httpx.AsyncClient) -> None:
    resp = await register(client, "alice@example.com")
    me = await client.get("/api/me")

    assert resp.status_code == 201
    assert resp.json()["user"]["email"] == "alice@example.com"
    assert resp.json()["user"]["role"] == "user"
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"
    assert set(me.json()) == {"id", "email", "role", "created_at"}


async def test_register_returns_tokens_in_the_body_and_sets_no_cookies(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    resp = await register(client, "alice@example.com")

    body = resp.json()
    assert set(body) == {"access_token", "access_expires_in", "refresh_token", "user"}
    assert body["access_expires_in"] == settings.access_token_ttl_minutes * 60
    assert body["access_token"] and body["refresh_token"]
    assert "set-cookie" not in resp.headers
    assert resp.headers["cache-control"] == "no-store"


async def test_csrf_endpoint_no_longer_exists(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/auth/csrf")).status_code == 404


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


async def test_login_with_correct_password_returns_a_working_session(
    new_client: ClientFactory,
) -> None:
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


async def test_refresh_rotates_the_refresh_token_and_returns_a_working_access_token(
    client: httpx.AsyncClient, new_client: ClientFactory
) -> None:
    old = (await register(client, "alice@example.com")).json()["refresh_token"]

    resp = await _refresh(client, old)

    body = resp.json()
    assert resp.status_code == 200
    assert body["refresh_token"] not in ("", old)
    assert body["user"]["email"] == "alice@example.com"
    other = await new_client()
    assert (await other.get("/api/me", headers=bearer(body["access_token"]))).status_code == 200


async def test_refresh_reusing_an_old_token_revokes_the_whole_family(
    client: httpx.AsyncClient,
) -> None:
    old = (await register(client, "alice@example.com")).json()["refresh_token"]
    newest = (await _refresh(client, old)).json()["refresh_token"]

    replay = await _refresh(client, old)
    legit = await _refresh(client, newest)

    assert replay.status_code == 401
    assert legit.status_code == 401  # the family died, including the legitimate newest token


async def test_refresh_without_a_body_returns_422_and_with_junk_returns_401(
    client: httpx.AsyncClient,
) -> None:
    missing = await _refresh(client, None)
    junk = await _refresh(client, "not-a-real-token")

    assert missing.status_code == 422
    assert junk.status_code == 401
    assert junk.json()["error"]["code"] == "unauthenticated"


async def test_refresh_ignores_a_refresh_cookie(client: httpx.AsyncClient) -> None:
    token = (await register(client, "alice@example.com")).json()["refresh_token"]
    client.cookies.set("se_refresh", token, domain="testserver.local", path="/api/auth")

    assert (await client.post("/api/auth/refresh")).status_code == 422


async def test_logout_revokes_the_family_and_returns_204(client: httpx.AsyncClient) -> None:
    refresh_token = (await register(client, "alice@example.com")).json()["refresh_token"]

    resp = await client.post("/api/auth/logout", json={"refresh_token": refresh_token})

    assert resp.status_code == 204
    assert (await _refresh(client, refresh_token)).status_code == 401


async def test_logout_with_an_already_rotated_token_still_revokes_the_family(
    client: httpx.AsyncClient,
) -> None:
    first = (await register(client, "alice@example.com")).json()["refresh_token"]
    second = (await _refresh(client, first)).json()["refresh_token"]

    await client.post("/api/auth/logout", json={"refresh_token": first})

    assert (await _refresh(client, second)).status_code == 401


@pytest.mark.parametrize("token", ["", "unknown-token", "x" * 500])
async def test_logout_with_an_unknown_token_returns_204_like_a_real_one(
    client: httpx.AsyncClient, token: str
) -> None:
    resp = await client.post("/api/auth/logout", json={"refresh_token": token})

    assert resp.status_code == 204


async def test_me_without_session_returns_401_envelope(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/me")

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthenticated"


@pytest.mark.parametrize(
    "header",
    ["garbage", "Bearer", "Bearer ", "Bearer garbage", "Basic abc", "Bearer a b", "Token xyz"],
)
async def test_me_with_a_malformed_authorization_header_returns_401(
    client: httpx.AsyncClient, header: str
) -> None:
    resp = await client.get("/api/me", headers={"Authorization": header})

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthenticated"


async def test_me_accepts_the_bearer_scheme_in_any_case(client: httpx.AsyncClient) -> None:
    token = (await register(client, "alice@example.com")).json()["access_token"]
    del client.headers["Authorization"]

    resp = await client.get("/api/me", headers={"Authorization": f"bearer {token}"})

    assert resp.status_code == 200


async def test_a_refresh_token_is_not_accepted_as_an_access_token(
    client: httpx.AsyncClient,
) -> None:
    refresh_token = (await register(client, "alice@example.com")).json()["refresh_token"]

    resp = await client.get("/api/me", headers=bearer(refresh_token))

    assert resp.status_code == 401


async def test_a_valid_access_jwt_in_the_old_cookie_is_not_authentication(
    client: httpx.AsyncClient, new_client: ClientFactory, settings: Settings
) -> None:
    # Safe only because nothing is cookie-authenticated any more (which is why CSRF is gone).
    user_id = (await register(client, "alice@example.com")).json()["user"]["id"]
    cookie_only = await new_client()
    cookie_only.cookies.set(
        "se_access",
        create_access_token(user_id, settings),
        domain="testserver.local",
        path="/api",
    )

    assert (await cookie_only.get("/api/me")).status_code == 401
    assert (await cookie_only.put("/api/watchlist/AAPL")).status_code == 401


async def test_refresh_for_disabled_user_returns_401(
    client: httpx.AsyncClient, db: Database
) -> None:
    token = (await register(client, "alice@example.com")).json()["refresh_token"]
    await db.users.update_one({}, {"$set": {"status": "disabled"}})

    assert (await _refresh(client, token)).status_code == 401


async def test_refresh_past_the_absolute_session_cap_returns_401(
    client: httpx.AsyncClient, db: Database, settings: Settings
) -> None:
    token = (await register(client, "alice@example.com")).json()["refresh_token"]
    cap = timedelta(days=settings.refresh_absolute_days)
    await db.refresh_tokens.update_many(
        {}, {"$set": {"family_started_at": datetime.now(UTC) - cap - timedelta(minutes=1)}}
    )

    assert (await _refresh(client, token)).status_code == 401


async def test_locked_users_existing_session_keeps_working(
    client: httpx.AsyncClient, new_client: ClientFactory, settings: Settings
) -> None:
    refresh_token = (await register(client, "alice@example.com")).json()["refresh_token"]
    attacker = await new_client()
    for _ in range(settings.login_max_failures):
        await login(attacker, "alice@example.com", "wrong-password-123")

    assert (await login(attacker, "alice@example.com")).status_code == 401  # locked out
    assert (await client.get("/api/me")).json()["email"] == "alice@example.com"
    assert (await _refresh(client, refresh_token)).status_code == 200


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


# --- CORS: exact origins, no credentials --------------------------------------------------------


async def test_cors_allowed_origin_gets_headers_but_no_credentials_flag(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    origin = settings.cors_origins[0]

    resp = await client.get("/api/health", headers={"Origin": origin})

    assert resp.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-credentials" not in resp.headers


@pytest.mark.parametrize(
    "origin", ["https://evil.example", "null", "http://localhost:5173.evil.io"]
)
async def test_cors_foreign_or_null_origin_gets_no_allow_origin_header(
    client: httpx.AsyncClient, origin: str
) -> None:
    simple = await client.get("/api/health", headers={"Origin": origin})
    preflight = await client.options(
        "/api/me",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert "access-control-allow-origin" not in simple.headers
    assert "access-control-allow-origin" not in preflight.headers


async def test_cors_preflight_allows_authorization_but_not_the_old_csrf_header(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    async def preflight(headers: str) -> httpx.Response:
        return await client.options(
            "/api/me",
            headers={
                "Origin": settings.cors_origins[0],
                "Access-Control-Request-Method": "DELETE",
                "Access-Control-Request-Headers": headers,
            },
        )

    ok = await preflight("authorization, content-type")
    csrf = await preflight("x-csrf-token")

    assert ok.status_code == 200
    assert csrf.status_code == 400
