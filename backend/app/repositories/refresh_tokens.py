"""Refresh-token storage with rotation and reuse detection."""

from dataclasses import dataclass
from datetime import UTC, datetime

from bson import ObjectId
from pymongo import ASCENDING, ReturnDocument

from app.db import Database, Document


@dataclass(frozen=True, slots=True)
class RotatedToken:
    user_id: ObjectId
    family_id: str
    family_started_at: datetime  # when the login that began this family happened


async def install_indexes(db: Database) -> None:
    col = db.refresh_tokens
    await col.create_index([("token_hash", ASCENDING)], unique=True)
    await col.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
    await col.create_index([("family_id", ASCENDING)])
    await col.create_index([("user_id", ASCENDING)])


class RefreshTokensRepository:
    def __init__(self, db: Database) -> None:
        self._col = db.refresh_tokens

    async def issue(
        self,
        token_hash: str,
        user_id: ObjectId,
        family_id: str,
        expires_at: datetime,
        family_started_at: datetime,
    ) -> None:
        doc: Document = {
            "token_hash": token_hash,
            "user_id": user_id,
            "family_id": family_id,
            "expires_at": expires_at,
            "family_started_at": family_started_at,
            "used_at": None,
            "revoked_at": None,
        }
        await self._col.insert_one(doc)

    async def consume(self, token_hash: str) -> RotatedToken | None:
        """Mark a live token as used and return its owner and family.

        Returns None for unknown or expired tokens. Presenting a token that was already used or
        revoked is treated as theft: the whole family is revoked and None is returned.
        """
        now = datetime.now(UTC)
        doc = await self._col.find_one_and_update(
            {
                "token_hash": token_hash,
                "used_at": None,
                "revoked_at": None,
                "expires_at": {"$gt": now},
            },
            {"$set": {"used_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        if doc:
            return RotatedToken(
                user_id=doc["user_id"],
                family_id=doc["family_id"],
                # Absent only on tokens issued before the cap existed; those get a fresh window.
                family_started_at=doc.get("family_started_at", now),
            )
        stale = await self._col.find_one({"token_hash": token_hash})
        if stale:
            await self.revoke_family(stale["family_id"])
        return None

    async def revoke_family(self, family_id: str) -> None:
        await self._col.update_many(
            {"family_id": family_id, "revoked_at": None},
            {"$set": {"revoked_at": datetime.now(UTC)}},
        )

    async def revoke_by_hash(self, token_hash: str) -> None:
        doc = await self._col.find_one({"token_hash": token_hash})
        if doc:
            await self.revoke_family(doc["family_id"])

    async def revoke_for_user(self, user_id: ObjectId) -> None:
        """Revoke every live family of a user (sign them out everywhere)."""
        await self._col.update_many(
            {"user_id": user_id, "revoked_at": None},
            {"$set": {"revoked_at": datetime.now(UTC)}},
        )

    async def delete_for_user(self, user_id: ObjectId) -> None:
        await self._col.delete_many({"user_id": user_id})
