"""Admin user management.

Deliberately never imports the watchlist repository or router (enforced by import-linter):
admins manage accounts, not what users watch.
"""

from datetime import datetime
from typing import Annotated, Literal

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, ConfigDict

from app.api.deps import AdminDep, DbDep, SettingsDep
from app.auth.passwords import Argon2Hasher
from app.repositories.users import UserRecord
from app.services.accounts import AccountService, AppError

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminUserOut(BaseModel):
    id: str
    email: str
    role: str
    status: str
    created_at: datetime
    last_login_at: datetime | None


class AdminUserPage(BaseModel):
    items: list[AdminUserOut]
    total: int


class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "disabled"] | None = None
    role: Literal["user", "admin"] | None = None


def _out(user: UserRecord) -> AdminUserOut:
    return AdminUserOut(
        id=str(user.id),
        email=user.email,
        role=user.role,
        status=user.status,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


def _object_id(raw: str) -> ObjectId:
    try:
        return ObjectId(raw)
    except InvalidId as exc:
        raise AppError(404, "not_found", "User not found.") from exc


@router.get("/users")
async def list_users(
    _admin: AdminDep,
    db: DbDep,
    settings: SettingsDep,
    query: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminUserPage:
    service = AccountService(db, settings, Argon2Hasher())
    users, total = await service.list_users(query, page, page_size)
    return AdminUserPage(items=[_out(u) for u in users], total=total)


@router.patch("/users/{user_id}")
async def patch_user(
    user_id: str, body: UserPatch, admin: AdminDep, db: DbDep, settings: SettingsDep
) -> AdminUserOut:
    service = AccountService(db, settings, Argon2Hasher())
    updated = await service.update_user(admin.id, _object_id(user_id), body.status, body.role)
    return _out(updated)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: str, admin: AdminDep, db: DbDep, settings: SettingsDep) -> Response:
    await AccountService(db, settings, Argon2Hasher()).delete_user(admin.id, _object_id(user_id))
    return Response(status_code=204)
