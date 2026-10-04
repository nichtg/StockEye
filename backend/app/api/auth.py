"""Registration, login, token refresh/rotation, logout and the CSRF token endpoint."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.deps import DbDep, SettingsDep
from app.auth.cookies import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    clear_auth_cookies,
    set_auth_cookies,
    set_csrf_cookie,
)
from app.auth.csrf import new_csrf_token
from app.auth.passwords import Argon2Hasher, PasswordPolicyError, validate_password
from app.auth.tokens import create_access_token, hash_refresh_token, new_refresh_token
from app.config import Settings
from app.db import Database
from app.repositories.refresh_tokens import RefreshTokensRepository
from app.repositories.users import UserRecord, UsersRepository
from app.services.accounts import AccountService

router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory, per process: adequate for a single instance; swap the storage URI to share limits.
limiter = Limiter(key_func=get_remote_address)
_AUTH_LIMIT = "10/minute"


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class RegisterIn(BaseModel):
    # Unknown fields (e.g. "role") are rejected so nobody can self-assign privileges.
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str

    @model_validator(mode="after")
    def _check_policy(self) -> "RegisterIn":
        try:
            validate_password(self.password, self.email)
        except PasswordPolicyError as exc:
            raise ValueError(str(exc)) from exc
        return self


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    created_at: datetime


class SessionOut(BaseModel):
    user: UserOut


class CsrfOut(BaseModel):
    csrf_token: str


def _user_out(user: UserRecord) -> UserOut:
    return UserOut(id=str(user.id), email=user.email, role=user.role, created_at=user.created_at)


def _account_service(db: Database, settings: Settings) -> AccountService:
    return AccountService(db, settings, Argon2Hasher())


async def _start_session(
    response: Response,
    db: Database,
    settings: Settings,
    user_id: ObjectId,
    family_id: str | None = None,
) -> None:
    """Issue an access JWT plus a fresh refresh token (new family unless rotating one)."""
    refresh = new_refresh_token()
    expires = datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days)
    await RefreshTokensRepository(db).issue(
        hash_refresh_token(refresh), user_id, family_id or uuid.uuid4().hex, expires
    )
    set_auth_cookies(response, settings, create_access_token(str(user_id), settings), refresh)


@router.get("/csrf")
async def csrf(response: Response, settings: SettingsDep) -> CsrfOut:
    token = new_csrf_token()
    set_csrf_cookie(response, settings, token)
    return CsrfOut(csrf_token=token)


@router.post("/register", status_code=201)
@limiter.limit(_AUTH_LIMIT)
async def register(
    request: Request, body: RegisterIn, response: Response, db: DbDep, settings: SettingsDep
) -> SessionOut:
    user = await _account_service(db, settings).register(body.email, body.password)
    await _start_session(response, db, settings, user.id)
    return SessionOut(user=_user_out(user))


@router.post("/login")
@limiter.limit(_AUTH_LIMIT)
async def login(
    request: Request, body: Credentials, response: Response, db: DbDep, settings: SettingsDep
) -> SessionOut:
    user = await _account_service(db, settings).authenticate(body.email, body.password)
    await _start_session(response, db, settings, user.id)
    return SessionOut(user=_user_out(user))


@router.post("/refresh")
async def refresh(
    response: Response,
    db: DbDep,
    settings: SettingsDep,
    se_refresh: Annotated[str | None, Cookie()] = None,
) -> SessionOut:
    unauthenticated = HTTPException(status_code=401, detail="Your session has expired.")
    if not se_refresh:
        raise unauthenticated
    # consume() revokes the whole family if this token was already used (theft signal).
    rotated = await RefreshTokensRepository(db).consume(hash_refresh_token(se_refresh))
    if rotated is None:
        clear_auth_cookies(response, settings)
        raise unauthenticated
    user = await UsersRepository(db).get_by_id(rotated.user_id)
    if user is None or user.status != "active":
        await RefreshTokensRepository(db).revoke_family(rotated.family_id)
        raise unauthenticated
    await _start_session(response, db, settings, user.id, rotated.family_id)
    return SessionOut(user=_user_out(user))


@router.post("/logout", status_code=204)
async def logout(
    db: DbDep,
    settings: SettingsDep,
    se_refresh: Annotated[str | None, Cookie()] = None,
) -> Response:
    if se_refresh:
        await RefreshTokensRepository(db).revoke_by_hash(hash_refresh_token(se_refresh))
    out = Response(status_code=204)
    clear_auth_cookies(out, settings)
    return out


__all__ = ["ACCESS_COOKIE", "REFRESH_COOKIE", "limiter", "router"]
