"""Shared FastAPI dependencies and their ``Annotated`` aliases."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.auth.principal import Principal
from app.config import Settings
from app.db import Database
from app.services.accounts import AccountService


def get_db(request: Request) -> Database:
    db: Database = request.app.state.db
    return db


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


DbDep = Annotated[Database, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def get_accounts(db: DbDep, settings: SettingsDep) -> AccountService:
    return AccountService(db, settings)


AccountsDep = Annotated[AccountService, Depends(get_accounts)]


def bearer_token(request: Request) -> str | None:
    """The token from ``Authorization: Bearer <token>``, or None if absent or malformed.

    This is the only place a credential is read from a request: cookies are ignored on purpose.
    """
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token or " " in token:
        return None
    return token


async def current_user(request: Request, accounts: AccountsDep) -> Principal:
    return await accounts.principal(bearer_token(request))


async def require_admin(user: Annotated[Principal, Depends(current_user)]) -> Principal:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    return user


UserDep = Annotated[Principal, Depends(current_user)]
AdminDep = Annotated[Principal, Depends(require_admin)]
