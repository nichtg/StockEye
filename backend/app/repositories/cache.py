"""Small key/value cache for computed payloads (quotes, searches, analysis reports).

Two clocks per entry: ``expires_at`` says when the payload stops being fresh, and ``stale_until``
(created + 7 days) says when it may no longer be used even as a fallback. Only ``stale_until``
has a TTL index: if Mongo deleted entries at ``expires_at`` there would be nothing left to serve
when a provider is down, which is exactly when the stale copy is most useful.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ValidationError

from app.db import Database
from app.logging_setup import get_logger

log = get_logger(__name__)

COLLECTION = "analysis_cache"
STALE_GRACE = timedelta(days=7)

type Payload = dict[str, Any]


async def install_indexes(db: Database) -> None:
    await db[COLLECTION].create_index("key", unique=True, name="key_unique")
    await db[COLLECTION].create_index("stale_until", expireAfterSeconds=0, name="ttl_stale_until")


@dataclass(frozen=True)
class CacheEntry:
    payload: Payload
    created_at: datetime
    expires_at: datetime

    def is_fresh(self, now: datetime) -> bool:
        return self.expires_at > now

    def parse[M: BaseModel](self, model: type[M], key: str) -> M | None:
        """The payload as ``model``, or None (a miss) if an older build saved another shape."""
        try:
            return model.model_validate(self.payload)
        except ValidationError:
            log.warning("cache_entry_invalid", key=key)
            return None


class CacheRepository:
    def __init__(self, db: Database) -> None:
        self._col = db[COLLECTION]

    async def lookup(self, key: str) -> CacheEntry | None:
        """The entry even if expired (until the 7 day grace ends); check ``is_fresh`` to use it."""
        doc = await self._col.find_one({"key": key})
        if doc is None:
            return None
        return CacheEntry(doc["payload"], doc["created_at"], doc["expires_at"])

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
