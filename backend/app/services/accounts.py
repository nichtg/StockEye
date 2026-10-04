"""Account use-cases: registration, login with lockout, and admin user management.

``AppError`` lives here (re-exported by ``app.api.errors``) because the layering contract lets
services raise it but forbids them from importing the API layer.
"""

from datetime import UTC, datetime, timedelta
from typing import Protocol

from bson import ObjectId

from app.config import Settings
from app.db import Database
from app.repositories.refresh_tokens import RefreshTokensRepository
from app.repositories.users import EmailTakenError, Role, Status, UserRecord, UsersRepository
from app.repositories.watchlists import WatchlistsRepository

_INVALID_LOGIN = "Incorrect email or password."


class AppError(Exception):
    """A domain-level failure with an HTTP status and a stable machine-readable code."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class PasswordHasherPort(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, password: str, password_hash: str) -> bool: ...
    def verify_dummy(self, password: str) -> None: ...
    def needs_rehash(self, password_hash: str) -> bool: ...


class AccountService:
    def __init__(self, db: Database, settings: Settings, hasher: PasswordHasherPort) -> None:
        self._users = UsersRepository(db)
        self._tokens = RefreshTokensRepository(db)
        self._watchlists = WatchlistsRepository(db)
        self._settings = settings
        self._hasher = hasher

    async def register(self, email: str, password: str, role: Role = "user") -> UserRecord:
        """Create an account. Callers must have validated the password policy already."""
        try:
            return await self._users.create(email, self._hasher.hash(password), role)
        except EmailTakenError as exc:
            raise AppError(409, "conflict", "An account with this email already exists.") from exc

    async def authenticate(self, email: str, password: str) -> UserRecord:
        user = await self._users.get_by_email(email)
        if user is None:
            # Burn comparable CPU so response time does not reveal whether the email exists.
            self._hasher.verify_dummy(password)
            raise AppError(401, "invalid_credentials", _INVALID_LOGIN)

        now = datetime.now(UTC)
        if user.locked_until is not None:
            if user.locked_until > now:
                raise AppError(
                    429,
                    "account_locked",
                    "Too many failed sign-in attempts. Please try again later.",
                )
            await self._users.clear_failures(user.id)  # lockout served; start counting afresh

        if not self._hasher.verify(password, user.password_hash):
            await self._users.record_failure(
                user.id,
                self._settings.login_max_failures,
                now + timedelta(minutes=self._settings.login_lockout_minutes),
            )
            raise AppError(401, "invalid_credentials", _INVALID_LOGIN)
        if user.status != "active":
            raise AppError(403, "account_disabled", "This account has been disabled.")

        new_hash = (
            self._hasher.hash(password) if self._hasher.needs_rehash(user.password_hash) else None
        )
        await self._users.record_login(user.id, new_hash)
        refreshed = await self._users.get_by_id(user.id)
        return refreshed or user

    async def list_users(
        self, query: str | None, page: int, page_size: int
    ) -> tuple[list[UserRecord], int]:
        return await self._users.list(query, page, page_size)

    async def update_user(
        self, actor_id: ObjectId, target_id: ObjectId, status: Status | None, role: Role | None
    ) -> UserRecord:
        target = await self._require(target_id)
        losing_admin = target.role == "admin" and (status == "disabled" or role == "user")
        if losing_admin:
            await self._guard_admin_removal(actor_id, target)
        updated = await self._users.update(target_id, status, role)
        if updated is None:
            raise AppError(404, "not_found", "User not found.")
        return updated

    async def delete_user(self, actor_id: ObjectId, target_id: ObjectId) -> None:
        """Delete the user, their refresh tokens and their watchlist document (not its contents)."""
        target = await self._require(target_id)
        if target.role == "admin":
            await self._guard_admin_removal(actor_id, target)
        elif actor_id == target_id:
            raise AppError(409, "conflict", "You cannot delete your own account.")
        await self._users.delete(target_id)
        await self._tokens.delete_for_user(target_id)
        await self._watchlists.delete_for_owner(target_id)

    async def _require(self, user_id: ObjectId) -> UserRecord:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise AppError(404, "not_found", "User not found.")
        return user

    async def _guard_admin_removal(self, actor_id: ObjectId, target: UserRecord) -> None:
        if actor_id == target.id:
            raise AppError(
                409, "conflict", "You cannot disable, demote or delete your own admin account."
            )
        if target.status == "active" and await self._users.count_active_admins() <= 1:
            raise AppError(409, "conflict", "The last active admin cannot be removed or demoted.")
