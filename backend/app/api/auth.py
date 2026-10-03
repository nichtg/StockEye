"""Registration, login, token refresh/rotation, logout and the CSRF token endpoint.

The account module owns every session decision; these handlers only turn its results into
cookies and JSON.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.api.deps import AccountsDep, SettingsDep
from app.api.limits import limiter
from app.auth.cookies import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    clear_auth_cookies,
    set_auth_cookies,
    set_csrf_cookie,
)
from app.auth.csrf import new_csrf_token
from app.auth.principal import Principal
from app.config import Settings
from app.repositories.users import Role, UserRecord
from app.services.accounts import SessionTokens

router = APIRouter(prefix="/auth", tags=["auth"])

_AUTH_LIMIT = "10/minute"


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class RegisterIn(BaseModel):
    # Unknown fields (e.g. "role") are rejected so nobody can self-assign privileges.
    # The password policy is enforced by AccountService.register, not here.
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    role: Role
    created_at: datetime

    @classmethod
    def of(cls, user: UserRecord | Principal) -> "UserOut":
        return cls(id=str(user.id), email=user.email, role=user.role, created_at=user.created_at)


class SessionOut(BaseModel):
    user: UserOut


class CsrfOut(BaseModel):
    csrf_token: str


def _sign_in(response: Response, settings: Settings, tokens: SessionTokens) -> None:
    """Set the session cookies and a fresh CSRF token (a new session must not reuse the old one)."""
    set_auth_cookies(response, settings, tokens.access, tokens.refresh)
    set_csrf_cookie(response, settings, new_csrf_token())


@router.get("/csrf")
async def csrf(response: Response, settings: SettingsDep) -> CsrfOut:
    token = new_csrf_token()
    set_csrf_cookie(response, settings, token)
    return CsrfOut(csrf_token=token)


@router.post("/register", status_code=201)
@limiter.limit(_AUTH_LIMIT)
async def register(
    request: Request,
    body: RegisterIn,
    response: Response,
    accounts: AccountsDep,
    settings: SettingsDep,
) -> SessionOut:
    user = await accounts.register(body.email, body.password)
    _sign_in(response, settings, await accounts.start_session(user))
    return SessionOut(user=UserOut.of(user))


@router.post("/login")
@limiter.limit(_AUTH_LIMIT)
async def login(
    request: Request,
    body: Credentials,
    response: Response,
    accounts: AccountsDep,
    settings: SettingsDep,
) -> SessionOut:
    user = await accounts.authenticate(body.email, body.password)
    _sign_in(response, settings, await accounts.start_session(user))
    return SessionOut(user=UserOut.of(user))


@router.post("/refresh")
async def refresh(
    response: Response,
    accounts: AccountsDep,
    settings: SettingsDep,
    se_refresh: Annotated[str | None, Cookie()] = None,
) -> SessionOut:
    tokens, user = await accounts.rotate(se_refresh)
    _sign_in(response, settings, tokens)
    return SessionOut(user=UserOut.of(user))


@router.post("/logout", status_code=204)
async def logout(
    accounts: AccountsDep,
    settings: SettingsDep,
    se_refresh: Annotated[str | None, Cookie()] = None,
) -> Response:
    await accounts.end_session(se_refresh)
    out = Response(status_code=204)
    clear_auth_cookies(out, settings)
    return out


__all__ = ["ACCESS_COOKIE", "REFRESH_COOKIE", "limiter", "router"]
