"""Registration, login, token refresh/rotation and logout.

Auth is bearer tokens in JSON bodies, never cookies: the SPA lives on another site, where
browsers drop third-party cookies. The account module owns every session decision; these
handlers only turn its results into JSON.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.api.deps import AccountsDep
from app.api.limits import AUTH, REFRESH, limited_by_ip
from app.auth.principal import Principal
from app.repositories.users import Role, UserRecord
from app.services.accounts import SessionTokens

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class RegisterIn(BaseModel):
    # Unknown fields (e.g. "role") are rejected so nobody can self-assign privileges.
    # The password policy is enforced by AccountService.register, not here.
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str


class RefreshIn(BaseModel):
    # No min length: logout must answer 204 for any junk, so there is no token-validity oracle.
    refresh_token: str = Field(max_length=512)


class UserOut(BaseModel):
    id: str
    email: str
    role: Role
    created_at: datetime

    @classmethod
    def of(cls, user: UserRecord | Principal) -> "UserOut":
        return cls(id=str(user.id), email=user.email, role=user.role, created_at=user.created_at)


class SessionOut(BaseModel):
    """A fresh token pair. The refresh token is single-use: store the one from the latest reply."""

    access_token: str
    access_expires_in: int = Field(description="Seconds until the access token expires.")
    refresh_token: str
    user: UserOut


def _session(tokens: SessionTokens, user: UserRecord) -> SessionOut:
    return SessionOut(
        access_token=tokens.access,
        access_expires_in=tokens.access_expires_in,
        refresh_token=tokens.refresh,
        user=UserOut.of(user),
    )


@router.post("/register", status_code=201, dependencies=[Depends(limited_by_ip(AUTH))])
async def register(body: RegisterIn, accounts: AccountsDep) -> SessionOut:
    user = await accounts.register(body.email, body.password)
    return _session(await accounts.start_session(user), user)


@router.post("/login", dependencies=[Depends(limited_by_ip(AUTH))])
async def login(body: Credentials, accounts: AccountsDep) -> SessionOut:
    user = await accounts.authenticate(body.email, body.password)
    return _session(await accounts.start_session(user), user)


@router.post("/refresh", dependencies=[Depends(limited_by_ip(REFRESH))])
async def refresh(body: RefreshIn, accounts: AccountsDep) -> SessionOut:
    tokens, user = await accounts.rotate(body.refresh_token)
    return _session(tokens, user)


@router.post("/logout", status_code=204, dependencies=[Depends(limited_by_ip(REFRESH))])
async def logout(body: RefreshIn, accounts: AccountsDep) -> Response:
    await accounts.end_session(body.refresh_token)
    return Response(status_code=204)
