import httpx
import pytest
from bson import ObjectId
from limits import parse

from app.config import RateLimits, Settings
from app.db import Database
from tests.integration.conftest import PASSWORD, ClientFactory, login, make_admin, register

pytestmark = pytest.mark.integration


@pytest.fixture
def settings(settings: Settings) -> Settings:
    settings.rate_limits = RateLimits(auth=parse("3/minute"))
    return settings


async def _delete(
    client: httpx.AsyncClient, password: str = PASSWORD, **kwargs: object
) -> httpx.Response:
    return await client.request("DELETE", "/api/me", json={"password": password}, **kwargs)  # type: ignore[arg-type]


async def test_delete_me_success_removes_everything_and_ends_session(
    new_client: ClientFactory, db: Database
) -> None:
    alice = await new_client()
    uid = ObjectId((await register(alice, "alice@example.com")).json()["user"]["id"])
    await alice.put("/api/watchlist/AAPL")
    refresh = alice.cookies.get("se_refresh", path="/api/auth")
    access = alice.cookies.get("se_access", path="/api")
    assert refresh and access

    resp = await _delete(alice)

    assert resp.status_code == 204
    set_cookies = " ".join(resp.headers.get_list("set-cookie"))
    assert "se_access=" in set_cookies and "se_refresh=" in set_cookies
    assert await db.users.find_one({"_id": uid}) is None
    assert await db.refresh_tokens.count_documents({"user_id": uid}) == 0
    assert await db.watchlists.find_one({"owner_id": uid}) is None
    replay = await new_client()
    replay.cookies.set("se_refresh", refresh, domain="testserver.local", path="/api/auth")
    replay.cookies.set("se_access", access, domain="testserver.local", path="/api")
    assert (await replay.post("/api/auth/refresh")).status_code == 401
    assert (await replay.get("/api/me")).status_code == 401


async def test_delete_me_wrong_password_returns_403_and_deletes_nothing(
    client: httpx.AsyncClient, db: Database
) -> None:
    uid = ObjectId((await register(client, "alice@example.com")).json()["user"]["id"])

    resp = await _delete(client, "not the password 123")

    assert resp.status_code == 403
    error = resp.json()["error"]
    assert error["code"] == "invalid_password"
    assert error["message"] == "That password is not correct."
    assert await db.users.find_one({"_id": uid}) is not None
    assert (await client.get("/api/me")).status_code == 200


async def test_delete_me_only_admin_returns_409(new_client: ClientFactory, db: Database) -> None:
    await make_admin(db)
    admin = await new_client()
    await login(admin, "root@example.com")

    resp = await _delete(admin)

    assert resp.status_code == 409
    assert resp.json()["error"]["message"] == (
        "You are the only admin. Make another user an admin before deleting your account."
    )
    assert await db.users.count_documents({"email": "root@example.com"}) == 1


async def test_delete_me_admin_with_another_admin_can_delete_themselves(
    new_client: ClientFactory, db: Database
) -> None:
    await make_admin(db, "root@example.com")
    await make_admin(db, "second@example.com")
    admin = await new_client()
    await login(admin, "root@example.com")

    resp = await _delete(admin)

    assert resp.status_code == 204
    assert await db.users.count_documents({"email": "root@example.com"}) == 0
    assert await db.users.count_documents({"email": "second@example.com"}) == 1


async def test_delete_me_without_csrf_header_returns_403(
    client: httpx.AsyncClient, db: Database
) -> None:
    await register(client, "alice@example.com")
    del client.headers["X-CSRF-Token"]

    resp = await _delete(client)

    assert resp.status_code == 403
    assert await db.users.count_documents({"email": "alice@example.com"}) == 1


async def test_delete_me_unauthenticated_returns_401(client: httpx.AsyncClient) -> None:
    assert (await _delete(client)).status_code == 401


async def test_delete_me_is_rate_limited_per_ip(client: httpx.AsyncClient) -> None:
    await register(client, "alice@example.com")  # spends 1 of the 3 auth hits

    statuses = [(await _delete(client, "wrong password 123")).status_code for _ in range(3)]

    assert statuses == [403, 403, 429]
