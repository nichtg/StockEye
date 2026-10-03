"""The account module: registration, login with lockout, sessions and admin user management.

One deep interface for everything about who a user is and whether they may be signed in. The
password, token and repository machinery stays behind it; routers only turn results into
cookies and JSON. ``AppError`` lives in ``app.services.errors`` (re-exported here and by
``app.api.errors``) because the layering contract lets services raise it but forbids them from
importing the API.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from bson import ObjectId

from app.auth import passwords
from app.auth.tokens import create_access_token, hash_refresh_token, new_refresh_token
from app.config import Settings
from app.db import Database
from app.repositories.refresh_tokens import RefreshTokensRepository
from app.repositories.users import EmailTakenError, Role, Status, UserRecord, UsersRepository
from app.repositories.watchlists import WatchlistsRepository
from app.services.errors import AppError

__all__ = ["AccountService", "AppError", "SessionTokens"]

_INVALID_LOGIN = "Incorrect email or password."
_SESSION_EXPIRED = "Your session has expired."


@dataclass(frozen=True, slots=True)
class SessionTokens:
    """Credentials for one session: a short-lived access JWT and an opaque refresh token."""

    access: str
    refresh: str


class AccountService:
    def __init__(self, db: Database, settings: Settings) -> None:
        self._users = UsersRepository(db)
        self._tokens = RefreshTokensRepository(db)
        self._watchlists = WatchlistsRepository(db)
        self._settings = settings

    async def register(self, email: str, password: str) -> UserRecord:
        """Create a regular user after applying the password policy.

        Raises ``AppError`` 422 (``validation_error``) for a policy violation and 409 for a
        duplicate email (case-insensitive).
        """
        _check_policy(email, password)
        try:
            return await self._users.create(email, passwords.hash_password(password))
        except EmailTakenError as exc:
            raise AppError(409, "conflict", "An account with this email already exists.") from exc

    async def create_or_promote_admin(self, email: str, password: str) -> tuple[UserRecord, bool]:
        """Create an admin, or promote (and re-enable) the existing user with this email.

        Returns the admin and whether it was newly created. An existing user keeps their
        password; the supplied one is only policy-checked.
        """
        _check_policy(email, password)
        try:
            created = await self._users.create(email, passwords.hash_password(password), "admin")
        except EmailTakenError:
            promoted = await self._users.promote_to_admin(email)
            if promoted is None:  # deleted between the two calls; extremely unlikely
                raise AppError(409, "conflict", "The account changed; please retry.") from None
            return promoted, False
        return created, True

    async def authenticate(self, email: str, password: str) -> UserRecord:
        """Verify credentials, enforcing lockout and the disabled flag.

        Unknown emails and wrong passwords raise the identical 401 and cost the same CPU.
        """
        user = await self._users.get_by_email(email)
        if user is None:
            passwords.verify_dummy(password)
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

        if not passwords.verify_password(password, user.password_hash):
            await self._users.record_failure(
                user.id,
                self._settings.login_max_failures,
                now + timedelta(minutes=self._settings.login_lockout_minutes),
            )
            raise AppError(401, "invalid_credentials", _INVALID_LOGIN)
        if user.status != "active":
            raise AppError(403, "account_disabled", "This account has been disabled.")

        new_hash = (
            passwords.hash_password(password)
            if passwords.needs_rehash(user.password_hash)
            else None
        )
        logged_in = await self._users.record_login(user.id, new_hash)
        if logged_in is None:  # deleted mid-login: indistinguishable from an unknown email
            raise AppError(401, "invalid_credentials", _INVALID_LOGIN)
        return logged_in

    async def start_session(self, user: UserRecord) -> SessionTokens:
        """Begin a new session (a new refresh-token family) for an authenticated user."""
        return await self._issue(user.id, uuid.uuid4().hex)

    async def rotate(self, raw_refresh: str | None) -> tuple[SessionTokens, UserRecord]:
        """Exchange a refresh token for a new pair, in the same family.

        Presenting an already-used or revoked token revokes its whole family (theft signal).
        Raises ``AppError`` 401 for a missing, unknown, expired, reused or disabled-user token.
        """
        if not raw_refresh:
            raise AppError(401, "unauthenticated", _SESSION_EXPIRED)
        rotated = await self._tokens.consume(hash_refresh_token(raw_refresh))
        if rotated is None:
            raise AppError(401, "unauthenticated", _SESSION_EXPIRED)
        user = await self._users.get_by_id(rotated.user_id)
        if user is None or user.status != "active":
            await self._tokens.revoke_family(rotated.family_id)
            raise AppError(401, "unauthenticated", _SESSION_EXPIRED)
        return await self._issue(user.id, rotated.family_id), user

    async def end_session(self, raw_refresh: str | None) -> None:
        """Sign out: revoke the refresh token's whole family. No-op without a token."""
        if raw_refresh:
            await self._tokens.revoke_by_hash(hash_refresh_token(raw_refresh))

    async def _issue(self, user_id: ObjectId, family_id: str) -> SessionTokens:
        refresh = new_refresh_token()
        expires = datetime.now(UTC) + timedelta(days=self._settings.refresh_token_ttl_days)
        await self._tokens.issue(hash_refresh_token(refresh), user_id, family_id, expires)
        return SessionTokens(create_access_token(str(user_id), self._settings), refresh)

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


def _check_policy(email: str, password: str) -> None:
    try:
        passwords.validate_password(password, email)
    except passwords.PasswordPolicyError as exc:
        message = str(exc)
        raise AppError(
            422, "validation_error", message, [{"field": "password", "message": message}]
        ) from exc
