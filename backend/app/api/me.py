"""The signed-in user's own profile."""

from fastapi import APIRouter

from app.api.auth import UserOut
from app.api.deps import UserDep

router = APIRouter(tags=["me"])


@router.get("/me")
async def me(user: UserDep) -> UserOut:
    # The auth dependency just read this user from the database; no second read.
    return UserOut.of(user)
