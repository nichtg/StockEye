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
from app.services.container import Services
from tests.services.fakes import (
    FakeClock,
    FakeMarketData,
    FakeNews,
    FakeScorer,
    build_fake_services,
)

PASSWORD = "correct-horse-battery"

type ClientFactory = Callable[[], Awaitable[httpx.AsyncClient]]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def provider(clock: FakeClock) -> FakeMarketData:
    return FakeMarketData(clock)


@pytest.fixture
def news_provider() -> FakeNews:
    return FakeNews()


@pytest.fixture
async def app(
    settings: Settings,
    db: Database,
    clock: FakeClock,
    provider: FakeMarketData,
    news_provider: FakeNews,
) -> AsyncIterator[FastAPI]:
    """The real app, with its services built around fake vendors (no network)."""

    async def factory(cfg: Settings, database: Database) -> Services:
        return build_fake_services(
            database,
            cfg,
            clock=clock,
            provider=provider,
            news_provider=news_provider,
            scorer=FakeScorer(),
        )

    application = create_app(settings, services_factory=factory)
    async with LifespanManager(application):
        yield application


@pytest.fixture
async def new_client(app: FastAPI) -> AsyncIterator[ClientFactory]:
    """Factory for independent anonymous clients; ``register`` and ``login`` sign them in."""
    opened: list[httpx.AsyncClient] = []

    async def factory() -> httpx.AsyncClient:
        client = httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")
        opened.append(client)
        return client

    yield factory
    for client in opened:
        await client.aclose()


@pytest.fixture
async def client(new_client: ClientFactory) -> httpx.AsyncClient:
    return await new_client()


def bearer(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def adopt_session(client: httpx.AsyncClient, resp: httpx.Response) -> httpx.Response:
    """Do what the SPA does: keep the access token and send it on every later request."""
    if resp.status_code < 400:
        client.headers.update(bearer(resp.json()["access_token"]))
    return resp


async def register(
    client: httpx.AsyncClient, email: str, password: str = PASSWORD
) -> httpx.Response:
    resp = await client.post("/api/auth/register", json={"email": email, "password": password})
    return adopt_session(client, resp)


async def make_admin(db: Database, email: str = "root@example.com") -> UserRecord:
    return await UsersRepository(db).create(email, await hash_password(PASSWORD), role="admin")


async def login(client: httpx.AsyncClient, email: str, password: str = PASSWORD) -> httpx.Response:
    resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    return adopt_session(client, resp)
