"""Quota types and the ledger port the guard depends on.

``app.providers`` and ``app.repositories`` are sibling layers and must not import each other, so
the guard talks to the MongoDB-backed ledger through these structural protocols. The concrete
dataclasses live in ``app.repositories.quotas`` and satisfy them by shape.
"""

from datetime import datetime
from typing import Literal, Protocol

from app.config import ProviderLimits

Window = Literal["minute", "day"]


class QuotaDecisionLike(Protocol):
    @property
    def allowed(self) -> bool: ...
    @property
    def window_blocked(self) -> Window | None: ...
    @property
    def used_today(self) -> int: ...
    @property
    def daily_limit(self) -> int: ...
    @property
    def retry_at(self) -> datetime | None: ...


class QuotaSnapshotLike(Protocol):
    @property
    def used_today(self) -> int: ...
    @property
    def daily_limit(self) -> int: ...
    @property
    def resets_at(self) -> datetime: ...


class QuotaLedgerLike(Protocol):
    async def try_consume(
        self, provider: str, limits: ProviderLimits, now: datetime
    ) -> QuotaDecisionLike: ...

    async def snapshot(
        self, provider: str, limits: ProviderLimits, now: datetime
    ) -> QuotaSnapshotLike: ...

    async def record_error(self, provider: str, message: str, now: datetime) -> None: ...

    async def last_error(self, provider: str) -> tuple[str, datetime] | None: ...
