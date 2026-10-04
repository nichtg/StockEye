"""Shared fixtures. Integration tests get a throwaway MongoDB database per test."""

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from pymongo import AsyncMongoClient

from app.config import Settings
from app.db import Database, Document, create_client

MONGODB_URI = os.environ.get("STOCKEYE_MONGODB_URI", "mongodb://127.0.0.1:27017")


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        mongodb_uri=MONGODB_URI,
        mongodb_db=f"stockeye_test_{uuid.uuid4().hex[:12]}",
        cookie_secure=False,
        scheduler_enabled=False,
    )


@pytest.fixture(scope="session")
async def mongo_client() -> AsyncIterator[AsyncMongoClient[Document]]:
    client = create_client(MONGODB_URI)
    try:
        await client.admin.command("ping")
    except Exception as exc:  # any connection failure means "no Mongo here"
        await client.close()
        pytest.skip(f"MongoDB not reachable at {MONGODB_URI}: {exc}")
    yield client
    await client.close()


@pytest.fixture
async def db(
    mongo_client: AsyncMongoClient[Document], settings: Settings
) -> AsyncIterator[Database]:
    database = mongo_client[settings.mongodb_db]
    yield database
    await mongo_client.drop_database(settings.mongodb_db)
