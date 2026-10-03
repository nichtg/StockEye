"""Request rate limits: one in-memory counter store, and the dependencies that spend from it.

``limited(bucket)`` budgets the data endpoints per signed-in user, so one account cannot spend
the shared vendor quotas by spreading requests over many addresses. ``limited_by_ip(bucket)``
does the same for the auth routes, keyed by client address since nobody is signed in yet (behind
a trusted proxy ``request.client.host`` is already the real client). Budgets come from
``Settings.rate_limits`` at request time. The counters live on the app instance
(``app.state.rate_limiter``), so every app, and so every test, starts with fresh ones.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from fastapi import Depends, Request
from limits import RateLimitItem
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter

from app.api.deps import SettingsDep, UserDep
from app.services.errors import AppError

type Bucket = Literal["search", "stock", "macro", "overview", "watchlist", "auth"]
SEARCH: Bucket = "search"
STOCK: Bucket = "stock"
MACRO: Bucket = "macro"
OVERVIEW: Bucket = "overview"
WATCHLIST: Bucket = "watchlist"
AUTH: Bucket = "auth"


class RateLimiter:
    """Fixed-window counters in process memory (swap the storage to share them across workers)."""

    def __init__(self) -> None:
        self._strategy = FixedWindowRateLimiter(MemoryStorage())

    def hit(self, budget: RateLimitItem, bucket: str, key: str) -> None:
        """Count one request; raise the 429 once ``key`` is past ``budget`` for ``bucket``."""
        if not self._strategy.hit(budget, bucket, key):
            raise AppError(
                429, "rate_limited", "Too many requests. Please slow down and try again shortly."
            )


def _limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter


LimiterDep = Annotated[RateLimiter, Depends(_limiter)]


def limited(bucket: Bucket) -> Callable[..., Awaitable[None]]:
    """A route dependency that counts the signed-in user's request against ``bucket``."""

    async def check(user: UserDep, limiter: LimiterDep, settings: SettingsDep) -> None:
        limiter.hit(getattr(settings.rate_limits, bucket), bucket, str(user.id))

    return check


def limited_by_ip(bucket: Bucket) -> Callable[..., Awaitable[None]]:
    """Like ``limited`` for routes with no signed-in user: keyed by the client address."""

    async def check(request: Request, limiter: LimiterDep, settings: SettingsDep) -> None:
        host = request.client.host if request.client else "unknown"
        limiter.hit(getattr(settings.rate_limits, bucket), bucket, host)

    return check
