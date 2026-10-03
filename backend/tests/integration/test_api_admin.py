import httpx
import pytest
from bson import ObjectId

from app.auth.passwords import Argon2Hasher
from app.config import Settings
from app.db import Database
from app.services.accounts import AccountService, AppError
from tests.integration.conftest import PASSWORD, ClientFactory, login, make_admin, register

pytestmark = pytest.mark.integration


async def _admin_client(new_client: ClientFactory, db: Database) -> httpx.AsyncClient:
    await make_admin(db)
    admin = await new_client()
    assert (await login(admin, "root@example.com")).status_code == 200
    return admin


async def test_admin_endpoints_for_normal_user_return_403(client: httpx.AsyncClient) -> None:
    await register(client, "alice@example.com")

    resp = await client.get("/api/admin/users")

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


async def test_admin_endpoints_without_session_return_401(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/admin/users")).status_code == 401


async def test_admin_list_has_no_watchlist_fields_and_supports_search(
    new_client: ClientFactory, db: Database
) -> None:
    admin = await _admin_client(new_client, db)
    alice = await new_client()
    await register(alice, "alice@example.com")
    await alice.put("/api/watchlist/AAPL")

    resp = await admin.get("/api/admin/users", params={"query": "ALIC"})

    body = resp.json()
    assert resp.status_code == 200
    assert body["total"] == 1
    item = body["items"][0]
    assert set(item) == {"id", "email", "role", "status", "created_at", "last_login_at"}
    assert "AAPL" not in resp.text
    assert "watchlist" not in resp.text.lower()


async def test_admin_list_paginates(new_client: ClientFactory, db: Database) -> None:
    admin = await _admin_client(new_client, db)
    for i in range(3):
        await register(await new_client(), f"user{i}@example.com")

    page2 = await admin.get("/api/admin/users", params={"page": 2, "page_size": 2})

    assert page2.json()["total"] == 4
    assert len(page2.json()["items"]) == 2


async def test_admin_get_watchlist_returns_only_admins_own_list(
    new_client: ClientFactory, db: Database
) -> None:
    admin = await _admin_client(new_client, db)
    alice = await new_client()
    await register(alice, "alice@example.com")
    await alice.put("/api/watchlist/AAPL")
    await admin.put("/api/watchlist/MSFT")

    resp = await admin.get("/api/watchlist")

    assert resp.json() == {"symbols": ["MSFT"]}


async def test_admin_cannot_demote_or_disable_themselves(
    new_client: ClientFactory, db: Database
) -> None:
    admin = await _admin_client(new_client, db)
    me_id = (await admin.get("/api/me")).json()["id"]

    demote = await admin.patch(f"/api/admin/users/{me_id}", json={"role": "user"})
    disable = await admin.patch(f"/api/admin/users/{me_id}", json={"status": "disabled"})
    delete = await admin.delete(f"/api/admin/users/{me_id}")

    assert demote.status_code == disable.status_code == delete.status_code == 409
    assert "own" in demote.json()["error"]["message"]


async def test_account_service_refuses_to_remove_the_last_active_admin(
    settings: Settings, db: Database
) -> None:
    only_admin = await make_admin(db)
    service = AccountService(db, settings, Argon2Hasher())
    someone_else = ObjectId()

    with pytest.raises(AppError) as demote:
        await service.update_user(someone_else, only_admin.id, None, "user")
    with pytest.raises(AppError) as delete:
        await service.delete_user(someone_else, only_admin.id)

    assert demote.value.status == delete.value.status == 409
    assert "last active admin" in demote.value.message


async def test_admin_can_demote_another_admin_when_one_remains(
    new_client: ClientFactory, db: Database
) -> None:
    admin = await _admin_client(new_client, db)
    other = await make_admin(db, "second@example.com")

    resp = await admin.patch(f"/api/admin/users/{other.id}", json={"role": "user"})

    assert resp.status_code == 200
    assert resp.json()["role"] == "user"


async def test_admin_patch_ignores_unknown_fields_with_422(
    new_client: ClientFactory, db: Database
) -> None:
    admin = await _admin_client(new_client, db)
    alice = await new_client()
    uid = (await register(alice, "alice@example.com")).json()["user"]["id"]

    resp = await admin.patch(f"/api/admin/users/{uid}", json={"password_hash": "x"})

    assert resp.status_code == 422


async def test_admin_patch_unknown_user_returns_404(
    new_client: ClientFactory, db: Database
) -> None:
    admin = await _admin_client(new_client, db)

    resp = await admin.patch(f"/api/admin/users/{ObjectId()}", json={"status": "disabled"})
    bad_id = await admin.patch("/api/admin/users/not-an-id", json={"status": "disabled"})

    assert resp.status_code == bad_id.status_code == 404


async def test_admin_delete_user_also_removes_their_watchlist_and_tokens(
    new_client: ClientFactory, db: Database
) -> None:
    admin = await _admin_client(new_client, db)
    alice = await new_client()
    uid = (await register(alice, "alice@example.com")).json()["user"]["id"]
    await alice.put("/api/watchlist/AAPL")
    assert await db.watchlists.find_one({"owner_id": ObjectId(uid)}) is not None

    resp = await admin.delete(f"/api/admin/users/{uid}")

    assert resp.status_code == 204
    assert await db.users.find_one({"_id": ObjectId(uid)}) is None
    assert await db.watchlists.find_one({"owner_id": ObjectId(uid)}) is None
    assert await db.refresh_tokens.count_documents({"user_id": ObjectId(uid)}) == 0
    assert (await alice.get("/api/me")).status_code == 401


async def test_disabled_user_existing_access_cookie_stops_working_immediately(
    new_client: ClientFactory, db: Database
) -> None:
    admin = await _admin_client(new_client, db)
    alice = await new_client()
    uid = (await register(alice, "alice@example.com")).json()["user"]["id"]
    assert (await alice.get("/api/me")).status_code == 200

    await admin.patch(f"/api/admin/users/{uid}", json={"status": "disabled"})

    assert (await alice.get("/api/me")).status_code == 401
    relogin = await login(await new_client(), "alice@example.com", PASSWORD)
    assert relogin.status_code == 403
    assert relogin.json()["error"]["code"] == "account_disabled"


async def test_demoted_admin_loses_access_immediately(
    new_client: ClientFactory, db: Database
) -> None:
    admin = await _admin_client(new_client, db)
    second = await make_admin(db, "second@example.com")
    second_client = await new_client()
    await login(second_client, "second@example.com")
    assert (await second_client.get("/api/admin/users")).status_code == 200

    await admin.patch(f"/api/admin/users/{second.id}", json={"role": "user"})

    assert (await second_client.get("/api/admin/users")).status_code == 403
