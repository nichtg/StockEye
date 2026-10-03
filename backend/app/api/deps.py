"""Shared FastAPI dependencies and their ``Annotated`` aliases."""

from datetime import UTC, datetime
from typing import Annotated

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, HTTPException, Request

from app.auth.cookies import ACCESS_COOKIE
from app.auth.principal import Principal
from app.auth.tokens import TokenError, decode_access_token
from app.config import Settings
from app.db import Database
from app.repositories.users import UsersRepository


def get_db(request: Request) -> Database:
    db: Database = request.app.state.db
    return db


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


DbDep = Annotated[Database, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def _unauthenticated() -> HTTPException:
    return HTTPException(status_code=401, detail="Please sign in to continue.")


async def current_user(request: Request, db: DbDep, settings: SettingsDep) -> Principal:
    """Resolve the caller from the access cookie, re-reading the user on every request.

    Hitting the DB each time means disabling a user or changing a role applies immediately.
    """
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise _unauthenticated()
    try:
        user_id = ObjectId(decode_access_token(token, settings))
    except (TokenError, InvalidId) as exc:
        raise _unauthenticated() from exc
    user = await UsersRepository(db).get_by_id(user_id)
    if user is None or user.status != "active":
        raise _unauthenticated()
    if user.locked_until is not None and user.locked_until > datetime.now(UTC):
        raise _unauthenticated()
    return Principal(id=user.id, email=user.email, role=user.role)


async def require_admin(user: Annotated[Principal, Depends(current_user)]) -> Principal:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    return user


UserDep = Annotated[Principal, Depends(current_user)]
AdminDep = Annotated[Principal, Depends(require_admin)]
