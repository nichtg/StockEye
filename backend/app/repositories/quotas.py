"""Fixed-window call quotas per provider, plus last-error health, in MongoDB.

Consumption is atomic: one ``find_one_and_update`` guarded by ``used < limit`` on a document
unique per (provider, window, start). A duplicate-key error on the upsert means the document
exists and is full.
"""

import math
from datetime import UTC, datetime, timedelta

from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.config import ProviderLimits
from app.db import Database, Document
from app.logging_setup import get_logger
from app.providers.quota import Priority, QuotaDecision, QuotaSnapshot, Window, daily_cap

log = get_logger(__name__)

QUOTA = "provider_quota"
HEALTH = "provider_health"
DEFAULT_WARNING_RATIO = 0.8


def _minute_start(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(second=0, microsecond=0)


def _day_start(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


async def install_indexes(db: Database) -> None:
    await db[QUOTA].create_index(
        [("provider", ASCENDING), ("window", ASCENDING), ("start", ASCENDING)],
        unique=True,
        name="provider_window_start",
    )
    # Old windows are useless after a few days; let Mongo prune them.
    await db[QUOTA].create_index("expires_at", expireAfterSeconds=0, name="ttl_expires_at")
    await db[HEALTH].create_index("provider", unique=True, name="provider_unique")


class QuotaLedger:
    def __init__(self, db: Database, warning_ratio: float = DEFAULT_WARNING_RATIO) -> None:
        self._db = db
        self._warning_ratio = warning_ratio

    async def _bump(
        self, provider: str, window: Window, start: datetime, limit: int, ttl: timedelta
    ) -> Document | None:
        """Atomically add one call to a window. None means the window is already full."""
        try:
            return await self._db[QUOTA].find_one_and_update(
                {"provider": provider, "window": window, "start": start, "used": {"$lt": limit}},
                {"$inc": {"used": 1}, "$setOnInsert": {"expires_at": start + ttl}},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            return None

    async def _flag_once(self, provider: str, window: Window, start: datetime, flag: str) -> bool:
        """Set ``flag`` on the window document only if unset; True means we were first."""
        result = await self._db[QUOTA].update_one(
            {"provider": provider, "window": window, "start": start, flag: {"$ne": True}},
            {"$set": {flag: True}},
        )
        return result.modified_count == 1

    async def try_consume(
        self, provider: str, limits: ProviderLimits, now: datetime, priority: Priority
    ) -> QuotaDecision:
        """Consume one call from the minute then the day window; log loudly near/at the limit.

        Interactive calls stop at their share of the day (see ``daily_cap``); scheduled calls may
        use all of it.
        """
        minute = _minute_start(now)
        day = _day_start(now)
        resets_at = day + timedelta(days=1)

        minute_doc = await self._bump(
            provider, "minute", minute, limits.per_minute, timedelta(hours=1)
        )
        if minute_doc is None:
            retry_at = minute + timedelta(minutes=1)
            if await self._flag_once(provider, "minute", minute, "blocked_logged"):
                log.warning(
                    "provider_rate_throttled",
                    provider=provider,
                    limit_per_minute=limits.per_minute,
                    retry_at=retry_at.isoformat(),
                )
            return QuotaDecision(
                False, "minute", await self._used_today(provider, day), limits.per_day, retry_at
            )

        day_cap = daily_cap(limits.per_day, priority)
        day_doc = await self._bump(provider, "day", day, day_cap, timedelta(days=3))
        if day_doc is None:
            # Roll back so a day-blocked call does not eat the minute budget.
            await self._db[QUOTA].update_one(
                {"provider": provider, "window": "minute", "start": minute},
                {"$inc": {"used": -1}},
            )
            await self._log_day_block(provider, day, limits, resets_at, priority)
            used = await self._used_today(provider, day)
            return QuotaDecision(False, "day", used, limits.per_day, resets_at)

        used = int(day_doc["used"])
        if used == 1:  # the upsert just created today's document
            await self._maybe_log_reset(provider, day)
        threshold = math.ceil(self._warning_ratio * limits.per_day)
        if used >= threshold and await self._flag_once(provider, "day", day, "warning_logged"):
            percent = round(self._warning_ratio * 100)
            log.warning(
                "provider_quota_warning",
                provider=provider,
                used=used,
                limit=limits.per_day,
                ratio=self._warning_ratio,
                resets_at=resets_at.isoformat(),
                message=(
                    f"Provider {provider} has used {used}/{limits.per_day} calls today "
                    f"({percent}%). Calls will be blocked at the limit until "
                    f"{resets_at.isoformat()}."
                ),
            )
        return QuotaDecision(True, None, used, limits.per_day, None)

    async def _log_day_block(
        self,
        provider: str,
        day: datetime,
        limits: ProviderLimits,
        resets_at: datetime,
        priority: Priority,
    ) -> None:
        """Log (once per day) why the day window refused a call: exhausted, or reserved."""
        day_cap = daily_cap(limits.per_day, priority)
        if priority == "scheduled":  # nothing is reserved from scheduled work: the day is spent
            if await self._flag_once(provider, "day", day, "blocked_logged"):
                log.error(
                    "provider_quota_exhausted",
                    provider=provider,
                    used=limits.per_day,
                    limit=limits.per_day,
                    resets_at=resets_at.isoformat(),
                )
        elif await self._flag_once(provider, "day", day, "reserved_logged"):
            log.warning(
                "provider_quota_reserved",
                provider=provider,
                used=day_cap,
                limit=limits.per_day,
                resets_at=resets_at.isoformat(),
                message=(
                    f"Interactive calls to {provider} are blocked: the last "
                    f"{limits.per_day - day_cap} of {limits.per_day} daily calls are reserved "
                    "for scheduled jobs."
                ),
            )

    async def _maybe_log_reset(self, provider: str, day: datetime) -> None:
        previous = await self._db[QUOTA].find_one(
            {"provider": provider, "window": "day", "start": {"$lt": day}},
            sort=[("start", -1)],
        )
        if previous and previous.get("warning_logged"):
            log.info(
                "provider_quota_reset",
                provider=provider,
                previous_used=previous.get("used"),
            )

    async def _used_today(self, provider: str, day: datetime) -> int:
        doc = await self._db[QUOTA].find_one({"provider": provider, "window": "day", "start": day})
        return int(doc["used"]) if doc else 0

    async def snapshot(self, provider: str, limits: ProviderLimits, now: datetime) -> QuotaSnapshot:
        day = _day_start(now)
        return QuotaSnapshot(
            await self._used_today(provider, day), limits.per_day, day + timedelta(days=1)
        )

    async def record_error(self, provider: str, message: str, now: datetime) -> None:
        await self._db[HEALTH].update_one(
            {"provider": provider},
            {"$set": {"last_error": message, "last_error_at": now}},
            upsert=True,
        )

    async def last_error(self, provider: str) -> tuple[str, datetime] | None:
        doc = await self._db[HEALTH].find_one({"provider": provider})
        if not doc or "last_error" not in doc:
            return None
        return str(doc["last_error"]), doc["last_error_at"]
