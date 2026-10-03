"""Atomic "add to a set unless it is full", shared by the watchlist and the ingest budget."""

from pymongo.asynchronous.collection import AsyncCollection
from pymongo.errors import DuplicateKeyError

from app.db import Document


async def add_to_capped_set(
    col: AsyncCollection[Document],
    owner_filter: Document,
    field: str,
    value: str,
    cap: int,
    *,
    also: Document | None = None,
) -> bool:
    """Idempotently add ``value`` to the ``field`` array of the one document matching
    ``owner_filter``; False if that would take the array past ``cap`` entries.

    The size guard lives in the filter so check and write are one atomic operation. When the
    guard fails the filter matches nothing, the upsert tries to insert a second document for the
    same owner, and the owner's unique index rejects it: that duplicate-key error is how "full"
    is detected. ``also`` holds further update operators to apply in the same write (e.g. ``$set``).
    """
    if cap <= 0:
        return False
    guard: Document = {"$or": [{field: value}, {f"{field}.{cap - 1}": {"$exists": False}}]}
    update: Document = {"$addToSet": {field: value}, **(also or {})}
    try:
        await col.update_one({**owner_filter, **guard}, update, upsert=True)
    except DuplicateKeyError:
        return False
    return True
