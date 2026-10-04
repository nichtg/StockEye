"""The signed-in user's own profile."""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import DbDep, UserDep
from app.repositories.users import UsersRepository

router = APIRouter(tags=["me"])


class MeOut(BaseModel):
    id: str
    email: str
    role: str
    created_at: datetime


@router.get("/me")
async def me(user: UserDep, db: DbDep) -> MeOut:
    record = await UsersRepository(db).get_by_id(user.id)
    if record is None:  # deleted between auth and now
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    return MeOut(
        id=str(record.id), email=record.email, role=record.role, created_at=record.created_at
    )
