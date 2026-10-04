"""The quota interface: decision and snapshot types plus the ledger port the guard depends on.

``QuotaLedgerPort`` is a seam with two adapters, the MongoDB ledger in
``app.repositories.quotas`` and an in-memory fake in tests. The value types live here, beside
the port, so both adapters and the guard share one definition.
"""

import math
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from app.config import ProviderLimits

Window = Literal["minute", "day"]
Priority = Literal["interactive", "scheduled"]

# Share of each provider's daily allowance that user-driven calls may consume. The remainder is
# reserved so the scheduled refreshes still run after a busy day of browsing.
INTERACTIVE_SHARE = 0.8

# Who is calling. A context variable (rather than a parameter on every service method) because
# background tasks started by a scheduled job inherit it, which is exactly the attribution wanted.
#
# Caveat: calls deduplicated by a ``SingleFlight`` run in the task of whichever caller started the
# flight, so they carry that caller's priority, and joiners with another priority inherit it. This
# is accepted: a shared fetch is charged once, to whoever happened to ask first.
_priority: ContextVar[Priority] = ContextVar("quota_priority", default="interactive")


def current_priority() -> Priority:
    return _priority.get()


@contextmanager
def scheduled_calls() -> Iterator[None]:
    """Mark every provider call made inside (and by tasks spawned inside) as scheduled work."""
    token = _priority.set("scheduled")
    try:
        yield
    finally:
        _priority.reset(token)


def daily_cap(per_day: int, priority: Priority) -> int:
    """Calls per day ``priority`` may consume: the whole allowance, or the interactive share."""
    return per_day if priority == "scheduled" else math.ceil(INTERACTIVE_SHARE * per_day)


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    window_blocked: Window | None
    used_today: int
    daily_limit: int
    retry_at: datetime | None


@dataclass(frozen=True)
class QuotaSnapshot:
    used_today: int
    daily_limit: int
    resets_at: datetime  # next 00:00 UTC


class QuotaLedgerPort(Protocol):
    async def try_consume(
        self, provider: str, limits: ProviderLimits, now: datetime, priority: Priority
    ) -> QuotaDecision: ...

    async def snapshot(
        self, provider: str, limits: ProviderLimits, now: datetime
    ) -> QuotaSnapshot: ...

    async def record_error(self, provider: str, message: str, now: datetime) -> None: ...

    async def last_error(self, provider: str) -> tuple[str, datetime] | None: ...
