"""Which never-before-seen symbols may start news ingestion, and how many each user may admit.

Ingestion of a new symbol costs dozens of vendor calls, so without a cap one account could burn
the shared free-tier quotas by walking through ticker symbols. One document per (user, day) holds
the symbols that user admitted, capped atomically. Each admission is also recorded per symbol
(who, when) at admit time: the scheduled job only backfills admitted symbols, and a second user
asking for a symbol that is admitted but still queued is not charged again.
"""

from datetime import datetime, timedelta

from bson import ObjectId
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

from app.db import Database
from app.repositories.capped_set import add_to_capped_set

COLLECTION = "ingest_budget"
ADMITTED = "admitted_symbols"


async def install_indexes(db: Database) -> None:
    await db[COLLECTION].create_index(
        [("user_id", ASCENDING), ("day", ASCENDING)], unique=True, name="user_day"
    )
    await db[COLLECTION].create_index("expires_at", expireAfterSeconds=0, name="ttl_expires_at")


class IngestBudget:
    def __init__(self, db: Database, per_day: int) -> None:
        self._col = db[COLLECTION]
        self._admitted = db[ADMITTED]
        self._per_day = per_day

    async def is_admitted(self, symbol: str) -> bool:
        return await self._admitted.find_one({"_id": symbol}, {"_id": 1}) is not None

    async def admit(self, user_id: ObjectId, symbol: str, now: datetime) -> bool:
        """Admit ``symbol`` on ``user_id``'s budget; False if that exceeds the daily cap.

        Free for a symbol already admitted by anyone, and idempotent per user and day. The
        symbol's record (its ``_id`` is unique) is the arbiter: whoever inserts it first is the
        only one who spends budget, and gives the record back if the budget is exhausted.
        """
        try:
            await self._admitted.insert_one({"_id": symbol, "user_id": user_id, "at": now})
        except DuplicateKeyError:
            return True
        spent = False
        try:
            spent = await add_to_capped_set(
                self._col,
                {"user_id": user_id, "day": now.date().isoformat()},
                "symbols",
                symbol,
                self._per_day,
                also={"$setOnInsert": {"expires_at": now + timedelta(days=2)}},
            )
        finally:
            # A refused or failed charge must not leave the symbol admitted for free.
            if not spent:
                await self._admitted.delete_one({"_id": symbol})
        return spent

    async def forget_user(self, user_id: ObjectId) -> None:
        """Drop a deleted user's budget documents and detach them from symbols they admitted.

        The admitted symbols themselves stay (the scheduled job still backfills them); only the
        pointer to the person goes.
        """
        await self._col.delete_many({"user_id": user_id})
        await self._admitted.update_many({"user_id": user_id}, {"$unset": {"user_id": ""}})
