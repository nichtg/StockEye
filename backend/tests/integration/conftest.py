"""Fixtures for API integration tests: a real app on a throwaway database."""

from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport

from app.auth.passwords import hash_password
from app.config import Settings
from app.db import Database
from app.main import create_app
from app.repositories.users import UserRecord, UsersRepository

PASSWORD = "correct-horse-battery"

type ClientFactory = Callable[[], Awaitable[httpx.AsyncClient]]


@pytest.fixture
async def app(settings: Settings, db: Database) -> AsyncIterator[FastAPI]:
    application = create_app(settings)
    async with LifespanManager(application):
        yield application


@pytest.fixture
async def new_client(app: FastAPI) -> AsyncIterator[ClientFactory]:
    """Factory for independent clients (separate cookie jars) with a CSRF token primed."""
    opened: list[httpx.AsyncClient] = []

    async def factory() -> httpx.AsyncClient:
        client = httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")
        opened.append(client)
        resp = await client.get("/api/auth/csrf")
        client.headers["X-CSRF-Token"] = resp.json()["csrf_token"]
        return client

    yield factory
    for client in opened:
        await client.aclose()


@pytest.fixture
async def client(new_client: ClientFactory) -> httpx.AsyncClient:
    return await new_client()


async def register(
    client: httpx.AsyncClient, email: str, password: str = PASSWORD
) -> httpx.Response:
    return await client.post("/api/auth/register", json={"email": email, "password": password})


async def make_admin(db: Database, email: str = "root@example.com") -> UserRecord:
    return await UsersRepository(db).create(email, hash_password(PASSWORD), role="admin")


async def login(client: httpx.AsyncClient, email: str, password: str = PASSWORD) -> httpx.Response:
    return await client.post("/api/auth/login", json={"email": email, "password": password})
