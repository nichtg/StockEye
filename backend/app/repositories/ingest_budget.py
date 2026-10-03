"""How many never-before-seen symbols each user may start news ingestion for, per UTC day.

Ingestion of a new symbol costs dozens of vendor calls, so without a cap one account could burn
the shared free-tier quotas by walking through ticker symbols. One document per (user, day) holds
the symbols already admitted; the size cap sits in the update filter so check and write are a
single atomic operation, as in the watchlist.
"""

from datetime import datetime, timedelta

from bson import ObjectId
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

from app.db import Database

COLLECTION = "ingest_budget"


async def install_indexes(db: Database) -> None:
    await db[COLLECTION].create_index(
        [("user_id", ASCENDING), ("day", ASCENDING)], unique=True, name="user_day"
    )
    await db[COLLECTION].create_index("expires_at", expireAfterSeconds=0, name="ttl_expires_at")


class IngestBudget:
    def __init__(self, db: Database, per_day: int) -> None:
        self._col = db[COLLECTION]
        self._per_day = per_day

    async def try_spend(self, user_id: ObjectId, symbol: str, now: datetime) -> bool:
        """Admit ``symbol`` for ``user_id`` today; False if that would exceed the daily cap.

        Idempotent per symbol: asking again for one already admitted today is free. When the
        cap is hit the filter matches nothing, the upsert tries to insert a second document for
        the (user, day) and the unique index rejects it, which is how "full" is detected.
        """
        if self._per_day <= 0:
            return False
        day = now.date().isoformat()
        room = {"$or": [{"symbols": symbol}, {f"symbols.{self._per_day - 1}": {"$exists": False}}]}
        try:
            await self._col.update_one(
                {"user_id": user_id, "day": day, **room},
                {
                    "$addToSet": {"symbols": symbol},
                    "$setOnInsert": {"expires_at": now + timedelta(days=2)},
                },
                upsert=True,
            )
        except DuplicateKeyError:
            return False
        return True
