"""Per-user watchlists. Every read requires the owner's id: there is no cross-user access."""

from datetime import UTC, datetime

from bson import ObjectId
from pymongo import ASCENDING

from app.db import Database
from app.repositories.capped_set import add_to_capped_set


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
        """Idempotently add ``symbol``; raise ``WatchlistFullError`` if it would exceed the cap."""
        added = await add_to_capped_set(
            self._col,
            {"owner_id": owner_id},
            "symbols",
            symbol,
            max_size,
            also={"$set": {"updated_at": datetime.now(UTC)}},
        )
        if not added:
            raise WatchlistFullError(max_size)

    async def remove(self, owner_id: ObjectId, symbol: str) -> None:
        await self._col.update_one(
            {"owner_id": owner_id},
            {"$pull": {"symbols": symbol}, "$set": {"updated_at": datetime.now(UTC)}},
        )

    async def all_symbols(self) -> list[str]:
        """Distinct symbols across all users. For background jobs only: it carries no user ids."""
        return sorted(await self._col.distinct("symbols"))

    async def delete_for_owner(self, owner_id: ObjectId) -> None:
        await self._col.delete_one({"owner_id": owner_id})
