"""Application factory. Run with ``uvicorn app.main:create_app --factory``.

Append new routers to ``ROUTERS`` and new repository index installers to ``INDEX_INSTALLERS``.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.api import admin, auth, health, me, watchlist
from app.api.errors import install_error_handlers
from app.api.middleware import CsrfMiddleware, RequestContextMiddleware
from app.config import Settings, get_settings
from app.db import IndexInstaller, create_client, ensure_indexes
from app.logging_setup import configure_logging, get_logger
from app.repositories import refresh_tokens, users, watchlists

ROUTERS: list[APIRouter] = [
    health.router,
    auth.router,
    me.router,
    watchlist.router,
    admin.router,
]

INDEX_INSTALLERS: list[IndexInstaller] = [
    users.install_indexes,
    refresh_tokens.install_indexes,
    watchlists.install_indexes,
]

log = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = create_client(settings.mongodb_uri)
        db = client[settings.mongodb_db]
        app.state.db = db
        app.state.settings = settings
        auth.limiter.reset()  # fresh counters per app instance (matters for tests)
        try:
            await ensure_indexes(db, INDEX_INSTALLERS)
        except Exception:
            await client.close()
            raise
        log.info("startup_complete", database=settings.mongodb_db)
        try:
            yield
        finally:
            await client.close()

    app = FastAPI(title="StockEye API", lifespan=lifespan)
    app.state.limiter = auth.limiter
    install_error_handlers(app)
    for router in ROUTERS:
        app.include_router(router, prefix="/api")

    # add_middleware wraps outward: the last one added runs first. CORS is outermost so even
    # error responses carry CORS headers; CSRF is innermost so its 403 gets a request id.
    app.add_middleware(CsrfMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    return app
