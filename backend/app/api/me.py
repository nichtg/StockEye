"""The signed-in user's own profile."""

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict

from app.api.auth import UserOut
from app.api.deps import AccountsDep, SettingsDep, UserDep
from app.api.limits import AUTH, limited_by_ip
from app.auth.cookies import clear_auth_cookies
from app.logging_setup import get_logger

router = APIRouter(tags=["me"])
log = get_logger(__name__)


class DeleteAccountIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str


@router.get("/me")
async def me(user: UserDep) -> UserOut:
    # The auth dependency just read this user from the database; no second read.
    return UserOut.of(user)


# Same per-IP budget as login: the password check here must not be a way to guess passwords.
@router.delete("/me", status_code=204, dependencies=[Depends(limited_by_ip(AUTH))])
async def delete_me(
    body: DeleteAccountIn, user: UserDep, accounts: AccountsDep, settings: SettingsDep
) -> Response:
    await accounts.delete_self(user, body.password)
    log.info("account_self_deleted", user_id=str(user.id))
    out = Response(status_code=204)
    clear_auth_cookies(out, settings)
    return out
