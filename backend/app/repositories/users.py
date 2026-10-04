"""User persistence. Returns frozen ``UserRecord`` values, never raw documents."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from bson import ObjectId
from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.db import Database, Document

type Role = Literal["user", "admin"]
# "deleting" is internal: a record claimed by an in-flight account deletion (see ``claim_admin``).
# It counts as neither an active admin nor a session-eligible user.
type Status = Literal["active", "disabled", "deleting"]
# What an admin may set; "deleting" is only ever written by the deletion flow.
type SettableStatus = Literal["active", "disabled"]


class EmailTakenError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class UserRecord:
    id: ObjectId
    email: str
    password_hash: str
    role: Role
    status: Status
    failed_logins: int
    locked_until: datetime | None
    created_at: datetime
    last_login_at: datetime | None


def _record(doc: Document) -> UserRecord:
    return UserRecord(
        id=doc["_id"],
        email=doc["email"],
        password_hash=doc["password_hash"],
        role=doc["role"],
        status=doc["status"],
        failed_logins=doc["failed_logins"],
        locked_until=doc["locked_until"],
        created_at=doc["created_at"],
        last_login_at=doc["last_login_at"],
    )


async def install_indexes(db: Database) -> None:
    await db.users.create_index([("email", ASCENDING)], unique=True)


class UsersRepository:
    def __init__(self, db: Database) -> None:
        self._col = db.users

    async def create(self, email: str, password_hash: str, role: Role = "user") -> UserRecord:
        doc: Document = {
            "_id": ObjectId(),
            "email": email.lower(),
            "password_hash": password_hash,
            "role": role,
            "status": "active",
            "failed_logins": 0,
            "locked_until": None,
            "created_at": datetime.now(UTC),
            "last_login_at": None,
        }
        try:
            await self._col.insert_one(doc)
        except DuplicateKeyError as exc:
            raise EmailTakenError(email) from exc
        return _record(doc)

    async def get_by_id(self, user_id: ObjectId) -> UserRecord | None:
        doc = await self._col.find_one({"_id": user_id})
        return _record(doc) if doc else None

    async def get_by_email(self, email: str) -> UserRecord | None:
        doc = await self._col.find_one({"email": email.lower()})
        return _record(doc) if doc else None

    async def list(
        self, query: str | None, page: int, page_size: int
    ) -> tuple[list[UserRecord], int]:
        """Page through users (1-based page); query is a case-insensitive email substring."""
        filt: Document = {"email": {"$regex": re.escape(query.lower())}} if query else {}
        total = await self._col.count_documents(filt)
        cursor = self._col.find(filt).sort("created_at", ASCENDING).skip((page - 1) * page_size)
        docs = await cursor.limit(page_size).to_list()
        return [_record(d) for d in docs], total

    async def count_active_admins(self) -> int:
        return await self._col.count_documents({"role": "admin", "status": "active"})

    async def update(
        self, user_id: ObjectId, status: Status | None, role: Role | None
    ) -> UserRecord | None:
        changes: Document = {}
        if status is not None:
            changes["status"] = status
        if role is not None:
            changes["role"] = role
        if not changes:
            return await self.get_by_id(user_id)
        doc = await self._col.find_one_and_update(
            {"_id": user_id}, {"$set": changes}, return_document=ReturnDocument.AFTER
        )
        return _record(doc) if doc else None

    async def delete(self, user_id: ObjectId) -> bool:
        result = await self._col.delete_one({"_id": user_id})
        return result.deleted_count == 1

    async def claim_admin(self, user_id: ObjectId) -> bool:
        """Atomically mark an active admin as ``deleting``; False if it is not one any more.

        Step one of removing an admin: the claim takes them out of the active-admin count, so
        the caller can check that someone is left *before* deleting, and nothing is ever
        re-inserted. A crash after the claim leaves a ``deleting`` record, never zero admins.
        """
        claimed = await self._col.find_one_and_update(
            {"_id": user_id, "role": "admin", "status": "active"},
            {"$set": {"status": "deleting"}},
        )
        return claimed is not None

    async def release_claim(self, user_id: ObjectId) -> None:
        """Undo ``claim_admin`` (the deletion would have removed the last active admin)."""
        await self._col.update_one(
            {"_id": user_id, "status": "deleting"}, {"$set": {"status": "active"}}
        )

    async def promote_to_admin(self, email: str) -> UserRecord | None:
        """Make the user with this email an active admin; None when no such user exists."""
        doc = await self._col.find_one_and_update(
            {"email": email.lower()},
            {"$set": {"role": "admin", "status": "active"}},
            return_document=ReturnDocument.AFTER,
        )
        return _record(doc) if doc else None

    async def reserve_attempt(
        self, user_id: ObjectId, max_failures: int, lock_until: datetime
    ) -> bool:
        """Atomically spend one password attempt; False when the account is already at the cap.

        The ``$lt`` guard sits in the filter, so under concurrency at most ``max_failures``
        callers can ever get True before a successful login resets the counter. The attempt
        that reaches the cap also sets the lock, in the same pipeline update.
        """
        result = await self._col.update_one(
            {"_id": user_id, "failed_logins": {"$lt": max_failures}},
            [
                {
                    "$set": {
                        "failed_logins": {"$add": ["$failed_logins", 1]},
                        # In one $set stage every expression sees the pre-increment document.
                        "locked_until": {
                            "$cond": [
                                {"$gte": [{"$add": ["$failed_logins", 1]}, max_failures]},
                                lock_until,
                                "$locked_until",
                            ]
                        },
                    }
                }
            ],
        )
        return result.modified_count == 1

    async def clear_expired_lock(self, user_id: ObjectId, now: datetime) -> None:
        """Reset the failure counter if (and only if) a lock has run out.

        Conditional so that a second request racing the first cannot wipe the counter again
        after the first has already started a new window.
        """
        await self._col.update_one(
            {"_id": user_id, "locked_until": {"$lte": now}},
            {"$set": {"failed_logins": 0, "locked_until": None}},
        )

    async def record_login(
        self, user_id: ObjectId, new_hash: str | None = None
    ) -> UserRecord | None:
        """Reset the failure counter, stamp the login and optionally swap in a rehashed password.

        Returns the updated record, or None if the user was deleted meanwhile.
        """
        changes: Document = {
            "failed_logins": 0,
            "locked_until": None,
            "last_login_at": datetime.now(UTC),
        }
        if new_hash is not None:
            changes["password_hash"] = new_hash
        doc = await self._col.find_one_and_update(
            {"_id": user_id}, {"$set": changes}, return_document=ReturnDocument.AFTER
        )
        return _record(doc) if doc else None
