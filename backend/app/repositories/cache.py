"""Small key/value cache for computed payloads (quotes, searches, analysis reports).

Two clocks per entry: ``expires_at`` says when the payload stops being fresh, and ``stale_until``
(created + 7 days) says when it may no longer be used even as a fallback. Only ``stale_until``
has a TTL index: if Mongo deleted entries at ``expires_at`` there would be nothing left to serve
when a provider is down, which is exactly when the stale copy is most useful.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from app.db import Database

COLLECTION = "analysis_cache"
STALE_GRACE = timedelta(days=7)

type Payload = dict[str, Any]


async def install_indexes(db: Database) -> None:
    await db[COLLECTION].create_index("key", unique=True, name="key_unique")
    await db[COLLECTION].create_index("stale_until", expireAfterSeconds=0, name="ttl_stale_until")


class CacheRepository:
    def __init__(self, db: Database) -> None:
        self._col = db[COLLECTION]

    async def get(self, key: str, now: datetime | None = None) -> Payload | None:
        """The payload if it is still fresh, else None."""
        doc = await self._col.find_one({"key": key})
        if doc is None:
            return None
        stamp = now or datetime.now(UTC)
        payload: Payload = doc["payload"]
        return payload if doc["expires_at"] > stamp else None

    async def get_stale(self, key: str) -> tuple[Payload, datetime] | None:
        """The payload and its creation time, even if expired (until the 7 day grace ends)."""
        doc = await self._col.find_one({"key": key})
        if doc is None:
            return None
        payload: Payload = doc["payload"]
        created: datetime = doc["created_at"]
        return payload, created

    async def put(
        self, key: str, payload: Payload, ttl: timedelta, now: datetime | None = None
    ) -> None:
        created = now or datetime.now(UTC)
        await self._col.replace_one(
            {"key": key},
            {
                "key": key,
                "payload": payload,
                "created_at": created,
                "expires_at": created + ttl,
                "stale_until": created + STALE_GRACE,
            },
            upsert=True,
        )
