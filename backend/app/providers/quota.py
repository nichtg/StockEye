"""The quota interface: decision and snapshot types plus the ledger port the guard depends on.

``QuotaLedgerPort`` is a seam with two adapters, the MongoDB ledger in
``app.repositories.quotas`` and an in-memory fake in tests. The value types live here, beside
the port, so both adapters and the guard share one definition.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from app.config import ProviderLimits

Window = Literal["minute", "day"]


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
        self, provider: str, limits: ProviderLimits, now: datetime
    ) -> QuotaDecision: ...

    async def snapshot(
        self, provider: str, limits: ProviderLimits, now: datetime
    ) -> QuotaSnapshot: ...

    async def record_error(self, provider: str, message: str, now: datetime) -> None: ...

    async def last_error(self, provider: str) -> tuple[str, datetime] | None: ...
