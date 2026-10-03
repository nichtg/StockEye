"""MongoDB connection lifecycle. One client per process, created at app startup."""

from collections.abc import Awaitable, Callable
from typing import Any

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

type Document = dict[str, Any]
type Database = AsyncDatabase[Document]
type IndexInstaller = Callable[[Database], Awaitable[None]]


def create_client(uri: str) -> AsyncMongoClient[Document]:
    return AsyncMongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=5000)


async def ensure_indexes(db: Database, installers: list[IndexInstaller]) -> None:
    """Run each repository's idempotent index installer."""
    for install in installers:
        await install(db)
