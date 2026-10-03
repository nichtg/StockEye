"""Request rate limits: the shared limiter, and per-user budgets for the data endpoints.

Auth routes use the limiter through slowapi's decorator (keyed by client address, since nobody is
signed in yet). The data endpoints use ``limited(bucket)`` instead, a dependency that reads its
budget from ``Settings.rate_limits`` at request time and keys by the signed-in user, so one
account cannot spend the shared vendor quotas by spreading requests over many addresses.
"""

from collections.abc import Awaitable, Callable
from contextlib import suppress

from fastapi import Request
from limits import parse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.deps import SettingsDep
from app.auth.cookies import ACCESS_COOKIE
from app.auth.tokens import TokenError, decode_access_token
from app.config import Settings
from app.services.errors import AppError

# In-memory, per process: adequate for a single instance; swap the storage URI to share limits.
limiter = Limiter(key_func=get_remote_address)

# The buckets ``Settings.rate_limits`` must define, one per kind of endpoint.
SEARCH = "search"
STOCK = "stock"  # shared by the quote, chart and technical endpoints of one user
MACRO = "macro"
OVERVIEW = "overview"


def user_or_ip_key(request: Request) -> str:
    """The signed-in user's id when the access cookie is valid, else the client address.

    Only the token's signature is checked (no database read): this key picks a counter, and the
    endpoint's own dependency still decides whether the caller is allowed in at all.
    """
    token = request.cookies.get(ACCESS_COOKIE)
    settings: Settings = request.app.state.settings
    if token:
        with suppress(TokenError):
            return f"user:{decode_access_token(token, settings)}"
    return f"ip:{get_remote_address(request)}"


def limited(bucket: str) -> Callable[[Request, Settings], Awaitable[None]]:
    """A route dependency that counts the request against ``bucket`` and 429s past its budget."""

    async def check(request: Request, settings: SettingsDep) -> None:
        budget = parse(settings.rate_limits[bucket])
        if not limiter.limiter.hit(budget, user_or_ip_key(request), bucket):
            raise AppError(
                429, "rate_limited", "Too many requests. Please slow down and try again shortly."
            )

    return check
