"""AccountService behaviour through its public interface, against a real MongoDB."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

from app.auth import passwords
from app.config import Settings
from app.db import Database, ensure_indexes
from app.main import INDEX_INSTALLERS
from app.repositories.users import UsersRepository
from app.services.accounts import AccountService, AppError

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery"
WRONG = "wrong-password-123"


@pytest.fixture
async def accounts(db: Database, settings: Settings) -> AccountService:
    await ensure_indexes(db, INDEX_INSTALLERS)  # the unique email index backs duplicate detection
    return AccountService(db, settings)


async def _raises(awaitable: object) -> AppError:
    with pytest.raises(AppError) as caught:
        await awaitable  # type: ignore[misc]
    return caught.value


async def test_register_creates_user_with_lowercased_email(accounts: AccountService) -> None:
    user = await accounts.register("Alice@Example.com", PASSWORD)

    assert (user.email, user.role, user.status) == ("alice@example.com", "user", "active")


async def test_register_weak_password_raises_422_with_password_field_detail(
    accounts: AccountService,
) -> None:
    error = await _raises(accounts.register("alice@example.com", "short"))

    assert (error.status, error.code) == (422, "validation_error")
    assert error.details == [{"field": "password", "message": error.message}]
    assert "at least 12" in error.message


async def test_register_password_equal_to_email_raises_422(accounts: AccountService) -> None:
    error = await _raises(accounts.register("longer.email@example.com", "LONGER.email@example.com"))

    assert error.status == 422


async def test_register_duplicate_email_raises_409_ignoring_case(accounts: AccountService) -> None:
    await accounts.register("alice@example.com", PASSWORD)

    error = await _raises(accounts.register("ALICE@example.com", PASSWORD))

    assert (error.status, error.code) == (409, "conflict")


async def test_authenticate_unknown_email_and_wrong_password_raise_identical_errors(
    accounts: AccountService,
) -> None:
    await accounts.register("alice@example.com", PASSWORD)

    wrong = await _raises(accounts.authenticate("alice@example.com", WRONG))
    unknown = await _raises(accounts.authenticate("nobody@example.com", WRONG))

    assert (wrong.status, wrong.code, wrong.message) == (
        unknown.status,
        unknown.code,
        unknown.message,
    )
    assert wrong.status == 401


async def test_authenticate_locks_after_max_failures_even_for_the_right_password(
    accounts: AccountService, settings: Settings
) -> None:
    await accounts.register("alice@example.com", PASSWORD)
    for _ in range(settings.login_max_failures):
        await _raises(accounts.authenticate("alice@example.com", WRONG))

    locked = await _raises(accounts.authenticate("alice@example.com", PASSWORD))

    assert (locked.status, locked.code) == (401, "invalid_credentials")


async def test_authenticate_after_lockout_expires_succeeds_and_resets_counters(
    accounts: AccountService, settings: Settings, db: Database
) -> None:
    await accounts.register("alice@example.com", PASSWORD)
    for _ in range(settings.login_max_failures):
        await _raises(accounts.authenticate("alice@example.com", WRONG))
    await db.users.update_one({}, {"$set": {"locked_until": datetime.now(UTC) - timedelta(days=1)}})

    user = await accounts.authenticate("alice@example.com", PASSWORD)

    assert (user.failed_logins, user.locked_until) == (0, None)
    assert user.last_login_at is not None


async def test_authenticate_failures_below_the_cap_do_not_lock(
    accounts: AccountService, settings: Settings
) -> None:
    await accounts.register("alice@example.com", PASSWORD)
    for _ in range(settings.login_max_failures - 1):
        await _raises(accounts.authenticate("alice@example.com", WRONG))

    user = await accounts.authenticate("alice@example.com", PASSWORD)

    assert user.email == "alice@example.com"


async def test_authenticate_disabled_user_raises_403(
    accounts: AccountService, db: Database
) -> None:
    await accounts.register("alice@example.com", PASSWORD)
    await db.users.update_one({}, {"$set": {"status": "disabled"}})

    error = await _raises(accounts.authenticate("alice@example.com", PASSWORD))

    assert (error.status, error.code) == (403, "account_disabled")


async def test_rotate_returns_fresh_tokens_and_the_user(accounts: AccountService) -> None:
    user = await accounts.register("alice@example.com", PASSWORD)
    first = await accounts.start_session(user)

    second, rotated_user = await accounts.rotate(first.refresh)

    assert rotated_user.id == user.id
    assert second.refresh != first.refresh
    assert second.access


async def test_rotate_reusing_a_token_revokes_the_whole_family(accounts: AccountService) -> None:
    user = await accounts.register("alice@example.com", PASSWORD)
    first = await accounts.start_session(user)
    second, _ = await accounts.rotate(first.refresh)

    replay = await _raises(accounts.rotate(first.refresh))
    newest = await _raises(accounts.rotate(second.refresh))

    assert replay.status == newest.status == 401


async def test_rotate_without_a_token_raises_401(accounts: AccountService) -> None:
    error = await _raises(accounts.rotate(None))

    assert (error.status, error.code) == (401, "unauthenticated")


async def test_rotate_for_disabled_user_raises_401_and_revokes_the_family(
    accounts: AccountService, db: Database
) -> None:
    user = await accounts.register("alice@example.com", PASSWORD)
    tokens = await accounts.start_session(user)
    await db.users.update_one({}, {"$set": {"status": "disabled"}})

    error = await _raises(accounts.rotate(tokens.refresh))

    assert error.status == 401
    assert await db.refresh_tokens.count_documents({"revoked_at": None}) == 0


async def test_end_session_revokes_the_family_and_tolerates_no_token(
    accounts: AccountService,
) -> None:
    user = await accounts.register("alice@example.com", PASSWORD)
    tokens = await accounts.start_session(user)

    await accounts.end_session(None)
    await accounts.end_session(tokens.refresh)

    assert (await _raises(accounts.rotate(tokens.refresh))).status == 401


async def test_update_user_cannot_demote_or_disable_own_admin_account(
    accounts: AccountService,
) -> None:
    admin, _ = await accounts.create_or_promote_admin("root@example.com", PASSWORD)

    demote = await _raises(accounts.update_user(admin.id, admin.id, None, "user"))
    disable = await _raises(accounts.update_user(admin.id, admin.id, "disabled", None))
    delete = await _raises(accounts.delete_user(admin.id, admin.id))

    assert demote.status == disable.status == delete.status == 409


async def test_update_user_refuses_to_remove_the_last_active_admin(
    accounts: AccountService,
) -> None:
    admin, _ = await accounts.create_or_promote_admin("root@example.com", PASSWORD)

    demote = await _raises(accounts.update_user(ObjectId(), admin.id, None, "user"))
    delete = await _raises(accounts.delete_user(ObjectId(), admin.id))

    assert demote.status == delete.status == 409
    assert "last active admin" in demote.message


async def test_delete_user_removes_user_and_refresh_tokens(
    accounts: AccountService, db: Database
) -> None:
    admin, _ = await accounts.create_or_promote_admin("root@example.com", PASSWORD)
    victim = await accounts.register("alice@example.com", PASSWORD)
    await accounts.start_session(victim)

    await accounts.delete_user(admin.id, victim.id)

    assert await UsersRepository(db).get_by_id(victim.id) is None
    assert await db.refresh_tokens.count_documents({"user_id": victim.id}) == 0


async def test_delete_user_unknown_id_raises_404(accounts: AccountService) -> None:
    error = await _raises(accounts.delete_user(ObjectId(), ObjectId()))

    assert error.status == 404


async def test_create_or_promote_admin_creates_a_new_admin(accounts: AccountService) -> None:
    admin, created = await accounts.create_or_promote_admin("Root@Example.com", PASSWORD)

    assert created
    assert (admin.email, admin.role) == ("root@example.com", "admin")


async def test_create_or_promote_admin_promotes_and_reenables_existing_user(
    accounts: AccountService, db: Database
) -> None:
    await accounts.register("alice@example.com", PASSWORD)
    await db.users.update_one({}, {"$set": {"status": "disabled"}})

    admin, created = await accounts.create_or_promote_admin("alice@example.com", PASSWORD)

    assert not created
    assert (admin.role, admin.status) == ("admin", "active")


async def test_create_or_promote_admin_rejects_weak_password(accounts: AccountService) -> None:
    error = await _raises(accounts.create_or_promote_admin("root@example.com", "short"))

    assert error.status == 422


# --- Eligibility, lockout and race conditions ---------------------------------------------------


async def test_principal_valid_token_returns_the_current_user(accounts: AccountService) -> None:
    user = await accounts.register("alice@example.com", PASSWORD)
    tokens = await accounts.start_session(user)

    principal = await accounts.principal(tokens.access)

    assert (principal.id, principal.email, principal.role) == (user.id, user.email, "user")


@pytest.mark.parametrize("token", [None, "", "garbage"])
async def test_principal_missing_or_invalid_token_raises_401(
    accounts: AccountService, token: str | None
) -> None:
    error = await _raises(accounts.principal(token))

    assert (error.status, error.code) == (401, "unauthenticated")


async def test_principal_disabled_user_raises_401(accounts: AccountService, db: Database) -> None:
    user = await accounts.register("alice@example.com", PASSWORD)
    tokens = await accounts.start_session(user)
    await db.users.update_one({}, {"$set": {"status": "disabled"}})

    error = await _raises(accounts.principal(tokens.access))

    assert error.status == 401


async def test_principal_deleted_user_raises_401(accounts: AccountService, db: Database) -> None:
    user = await accounts.register("alice@example.com", PASSWORD)
    tokens = await accounts.start_session(user)
    await db.users.delete_many({})

    assert (await _raises(accounts.principal(tokens.access))).status == 401


async def test_lockout_does_not_end_an_existing_session_or_refresh(
    accounts: AccountService, settings: Settings
) -> None:
    user = await accounts.register("alice@example.com", PASSWORD)
    tokens = await accounts.start_session(user)
    for _ in range(settings.login_max_failures):  # an attacker locks the account
        await _raises(accounts.authenticate("alice@example.com", WRONG))

    principal = await accounts.principal(tokens.access)
    rotated, _ = await accounts.rotate(tokens.refresh)

    assert principal.id == user.id
    assert rotated.access


async def test_locked_login_is_indistinguishable_from_unknown_email_and_pays_the_same_cpu(
    accounts: AccountService, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await accounts.register("alice@example.com", PASSWORD)
    for _ in range(settings.login_max_failures):
        await _raises(accounts.authenticate("alice@example.com", WRONG))
    dummy_runs: list[str] = []
    real_dummy = passwords.verify_dummy

    async def counting_dummy(password: str) -> None:
        dummy_runs.append(password)
        await real_dummy(password)

    monkeypatch.setattr(passwords, "verify_dummy", counting_dummy)

    locked = await _raises(accounts.authenticate("alice@example.com", PASSWORD))
    unknown = await _raises(accounts.authenticate("nobody@example.com", PASSWORD))

    assert (locked.status, locked.code, locked.message) == (
        unknown.status,
        unknown.code,
        unknown.message,
    )
    assert dummy_runs == [PASSWORD, PASSWORD]


async def test_concurrent_wrong_passwords_never_exceed_the_failure_cap(
    accounts: AccountService, settings: Settings, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    alice = await accounts.register("alice@example.com", PASSWORD)
    verifications = 0
    real_verify = passwords.verify_password

    async def counting_verify(password: str, password_hash: str) -> bool:
        nonlocal verifications
        verifications += password_hash == alice.password_hash  # not the dummy's verifications
        return await real_verify(password, password_hash)

    monkeypatch.setattr(passwords, "verify_password", counting_verify)

    results = await asyncio.gather(
        *(accounts.authenticate("alice@example.com", WRONG) for _ in range(25)),
        return_exceptions=True,
    )

    doc = await db.users.find_one({"email": "alice@example.com"})
    assert doc is not None
    assert all(isinstance(r, AppError) and r.status == 401 for r in results)
    assert doc["failed_logins"] == settings.login_max_failures
    assert doc["locked_until"] is not None
    # Only reserved attempts get to run argon2 verify; the other 20 were turned away.
    assert verifications == settings.login_max_failures


async def test_concurrent_demotions_of_two_admins_never_leave_zero(
    accounts: AccountService, db: Database
) -> None:
    repo = UsersRepository(db)
    first = await repo.create("a@example.com", "x", "admin")
    second = await repo.create("b@example.com", "x", "admin")

    await asyncio.gather(
        accounts.update_user(first.id, second.id, None, "user"),
        accounts.update_user(second.id, first.id, None, "user"),
        return_exceptions=True,
    )

    assert await repo.count_active_admins() >= 1


async def test_concurrent_disables_of_two_admins_never_leave_zero(
    accounts: AccountService, db: Database
) -> None:
    repo = UsersRepository(db)
    first = await repo.create("a@example.com", "x", "admin")
    second = await repo.create("b@example.com", "x", "admin")

    await asyncio.gather(
        accounts.update_user(first.id, second.id, "disabled", None),
        accounts.update_user(second.id, first.id, "disabled", None),
        return_exceptions=True,
    )

    assert await repo.count_active_admins() >= 1


async def test_concurrent_deletes_of_two_admins_never_leave_zero(
    accounts: AccountService, db: Database
) -> None:
    repo = UsersRepository(db)
    first = await repo.create("a@example.com", "x", "admin")
    second = await repo.create("b@example.com", "x", "admin")

    await asyncio.gather(
        accounts.delete_user(first.id, second.id),
        accounts.delete_user(second.id, first.id),
        return_exceptions=True,
    )

    assert await repo.count_active_admins() >= 1
