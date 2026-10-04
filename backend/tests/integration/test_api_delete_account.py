import asyncio
from datetime import UTC, datetime

import httpx
import pytest
from bson import ObjectId
from fastapi import FastAPI
from httpx import ASGITransport
from limits import parse

from app.auth.principal import Principal
from app.config import RateLimits, Settings
from app.db import Database
from app.repositories.ingest_budget import IngestBudget
from app.repositories.users import UsersRepository
from app.services.accounts import AccountService
from tests.integration.conftest import PASSWORD, ClientFactory, login, make_admin, register

pytestmark = pytest.mark.integration


@pytest.fixture
def settings(settings: Settings) -> Settings:
    settings.rate_limits = RateLimits(auth=parse("3/minute"))
    return settings


async def _delete(client: httpx.AsyncClient, password: str = PASSWORD) -> httpx.Response:
    return await client.request("DELETE", "/api/me", json={"password": password})


async def test_delete_me_success_removes_everything_and_ends_session(
    new_client: ClientFactory, db: Database
) -> None:
    alice = await new_client()
    uid = ObjectId((await register(alice, "alice@example.com")).json()["user"]["id"])
    assert (await alice.put("/api/watchlist/AAPL")).status_code == 200
    assert await db.watchlists.find_one({"owner_id": uid}) is not None
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


async def test_delete_me_per_account_limit_holds_when_the_ip_rotates(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    await register(client, "alice@example.com")
    statuses = []
    for i in range(4):
        transport = ASGITransport(app=app, client=(f"10.0.0.{i + 1}", 5000))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            cookies=client.cookies,
            headers=dict(client.headers),
        ) as rotated:
            statuses.append((await _delete(rotated, "wrong password 123")).status_code)

    assert statuses == [403, 403, 403, 429]


async def test_delete_me_removes_ingest_budget_and_detaches_admitted_symbols(
    client: httpx.AsyncClient, db: Database
) -> None:
    uid = ObjectId((await register(client, "alice@example.com")).json()["user"]["id"])
    assert await IngestBudget(db, 5).admit(uid, "ZZZZ", datetime.now(UTC))
    assert await db["ingest_budget"].count_documents({"user_id": uid}) == 1

    assert (await _delete(client)).status_code == 204

    assert await db["ingest_budget"].count_documents({"user_id": uid}) == 0
    admitted = await db["admitted_symbols"].find_one({"_id": "ZZZZ"})
    assert admitted is not None
    assert "user_id" not in admitted


async def test_delete_me_two_admins_deleting_at_once_never_leave_zero(
    new_client: ClientFactory, db: Database
) -> None:
    await make_admin(db, "root@example.com")
    await make_admin(db, "second@example.com")
    a, b = await new_client(), await new_client()
    await login(a, "root@example.com")
    await login(b, "second@example.com")

    results = await asyncio.gather(_delete(a), _delete(b))

    codes = sorted(r.status_code for r in results)
    assert codes.count(204) <= 1  # both may be refused (409); never both deleted
    assert await db.users.count_documents({"role": "admin", "status": "active"}) == 1


async def test_delete_user_crash_after_claim_leaves_a_deleting_record_not_zero_admins(
    db: Database, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await make_admin(db, "root@example.com")
    second = await make_admin(db, "second@example.com")
    service = AccountService(db, settings)
    principal = Principal(
        id=second.id, email=second.email, role="admin", created_at=second.created_at
    )

    async def boom(self: UsersRepository, user_id: ObjectId) -> bool:
        raise RuntimeError("crash")

    monkeypatch.setattr(UsersRepository, "delete", boom)
    with pytest.raises(RuntimeError):
        await service.delete_self(principal, PASSWORD)

    doc = await db.users.find_one({"_id": second.id})
    assert doc is not None
    assert doc["status"] == "deleting"
    assert await db.users.count_documents({"role": "admin", "status": "active"}) == 1


async def test_deleting_user_cannot_log_in_or_use_an_existing_session(
    new_client: ClientFactory, db: Database
) -> None:
    root = await make_admin(db, "root@example.com")
    admin = await new_client()
    await login(admin, "root@example.com")
    assert await UsersRepository(db).claim_admin(root.id)

    assert (await admin.get("/api/me")).status_code == 401
    assert (await login(await new_client(), "root@example.com")).status_code == 403


async def test_last_admin_refusal_does_not_leave_the_record_deleting(
    new_client: ClientFactory, db: Database
) -> None:
    await make_admin(db)
    admin = await new_client()
    await login(admin, "root@example.com")

    assert (await _delete(admin)).status_code == 409

    doc = await db.users.find_one({"email": "root@example.com"})
    assert doc is not None and doc["status"] == "active"
