"""Refresh-token storage: one record per family (a login) and one per issued token.

A family is the unit of revocation and of the absolute session cap, so both live on its record
and every rotation re-reads it. A token whose family record is missing is rejected (fail closed).
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from bson import ObjectId
from pymongo import ASCENDING, ReturnDocument

from app.db import Database, Document


@dataclass(frozen=True, slots=True)
class RotatedToken:
    user_id: ObjectId
    family_id: str


async def install_indexes(db: Database) -> None:
    tokens = db.refresh_tokens
    await tokens.create_index([("token_hash", ASCENDING)], unique=True)
    await tokens.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
    await tokens.create_index([("family_id", ASCENDING)])
    await tokens.create_index([("user_id", ASCENDING)])
    families = db.refresh_families
    await families.create_index([("user_id", ASCENDING)])
    # Cleanup only: past ``expires_at`` the cap has ended the family anyway, and a purged record
    # reads as missing, which is rejected like a revoked one.
    await families.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)


class RefreshTokensRepository:
    def __init__(self, db: Database) -> None:
        self._tokens = db.refresh_tokens
        self._families = db.refresh_families

    async def create_family(
        self, family_id: str, user_id: ObjectId, started_at: datetime, expires_at: datetime
    ) -> None:
        doc: Document = {
            "_id": family_id,
            "user_id": user_id,
            "started_at": started_at,
            "expires_at": expires_at,
            "revoked_at": None,
        }
        await self._families.insert_one(doc)

    async def family_is_live(self, family_id: str, started_after: datetime) -> bool:
        """Whether the family exists, is not revoked and began after ``started_after``."""
        doc = await self._families.find_one(
            {"_id": family_id, "revoked_at": None, "started_at": {"$gte": started_after}},
            projection={"_id": 1},
        )
        return doc is not None

    async def issue(
        self, token_hash: str, user_id: ObjectId, family_id: str, expires_at: datetime
    ) -> None:
        doc: Document = {
            "token_hash": token_hash,
            "user_id": user_id,
            "family_id": family_id,
            "expires_at": expires_at,
            "used_at": None,
        }
        await self._tokens.insert_one(doc)

    async def consume(self, token_hash: str) -> RotatedToken | None:
        """Mark an unused, unexpired token as used and return its owner and family.

        Returns None for unknown or expired tokens. Presenting a token that was already used (or
        has expired) is treated as theft: the whole family is revoked and None is returned.
        Whether the family itself is still live is the caller's check.
        """
        now = datetime.now(UTC)
        doc = await self._tokens.find_one_and_update(
            {"token_hash": token_hash, "used_at": None, "expires_at": {"$gt": now}},
            {"$set": {"used_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        if doc:
            return RotatedToken(user_id=doc["user_id"], family_id=doc["family_id"])
        stale = await self._tokens.find_one({"token_hash": token_hash})
        if stale:
            await self.revoke_family(stale["family_id"])
        return None

    async def revoke_family(self, family_id: str) -> None:
        """Set ``revoked_at`` once; later calls keep the first time."""
        await self._families.update_one(
            {"_id": family_id, "revoked_at": None}, {"$set": {"revoked_at": datetime.now(UTC)}}
        )

    async def revoke_by_hash(self, token_hash: str) -> None:
        stale = await self._tokens.find_one({"token_hash": token_hash})
        if stale:
            await self.revoke_family(stale["family_id"])

    async def revoke_for_user(self, user_id: ObjectId) -> None:
        """Revoke every live family of a user (sign them out everywhere)."""
        await self._families.update_many(
            {"user_id": user_id, "revoked_at": None}, {"$set": {"revoked_at": datetime.now(UTC)}}
        )

    async def delete_for_user(self, user_id: ObjectId) -> None:
        await self._tokens.delete_many({"user_id": user_id})
        await self._families.delete_many({"user_id": user_id})
