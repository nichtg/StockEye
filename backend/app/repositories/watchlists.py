"""Per-user watchlists. Every read requires the owner's id: there is no cross-user access."""

from datetime import UTC, datetime

from bson import ObjectId
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

from app.db import Database, Document


class WatchlistFullError(Exception):
    pass


async def install_indexes(db: Database) -> None:
    await db.watchlists.create_index([("owner_id", ASCENDING)], unique=True)


class WatchlistsRepository:
    def __init__(self, db: Database) -> None:
        self._col = db.watchlists

    async def get(self, owner_id: ObjectId) -> list[str]:
        doc = await self._col.find_one({"owner_id": owner_id})
        return list(doc["symbols"]) if doc else []

    async def add(self, owner_id: ObjectId, symbol: str, max_size: int) -> None:
        """Idempotently add ``symbol``; raise ``WatchlistFullError`` if it would exceed the cap.

        The size guard lives in the filter so check and write are one atomic operation. When the
        guard fails, the upsert tries to insert a second document for the owner, which the unique
        index rejects: that duplicate-key error is how "full" is detected.
        """
        guard: Document = {
            "$or": [{"symbols": symbol}, {f"symbols.{max_size - 1}": {"$exists": False}}]
        }
        try:
            await self._col.update_one(
                {"owner_id": owner_id, **guard},
                {
                    "$addToSet": {"symbols": symbol},
                    "$set": {"updated_at": datetime.now(UTC)},
                },
                upsert=True,
            )
        except DuplicateKeyError as exc:
            raise WatchlistFullError(max_size) from exc

    async def remove(self, owner_id: ObjectId, symbol: str) -> None:
        await self._col.update_one(
            {"owner_id": owner_id},
            {"$pull": {"symbols": symbol}, "$set": {"updated_at": datetime.now(UTC)}},
        )

    async def delete_for_owner(self, owner_id: ObjectId) -> None:
        await self._col.delete_one({"owner_id": owner_id})
