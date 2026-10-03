"""The caller's own watchlist. Only ever keyed by the authenticated principal's id."""

import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import DbDep, UserDep
from app.api.limits import OVERVIEW, limited
from app.repositories.watchlists import WatchlistFullError, WatchlistsRepository
from app.services.container import ServicesDep
from app.services.errors import AppError
from app.services.overview import OverviewRow, build_overview

router = APIRouter(tags=["watchlist"])

MAX_SYMBOLS = 50
_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")


class WatchlistOut(BaseModel):
    symbols: list[str]


def _normalise(symbol: str) -> str:
    cleaned = symbol.strip().upper()
    if not _SYMBOL_RE.fullmatch(cleaned):
        raise AppError(422, "validation_error", "Symbol must be 1-15 letters, digits, . or -.")
    return cleaned


@router.get("/watchlist")
async def get_watchlist(user: UserDep, db: DbDep) -> WatchlistOut:
    return WatchlistOut(symbols=await WatchlistsRepository(db).get(user.id))


@router.get("/watchlist/overview", dependencies=[Depends(limited(OVERVIEW))])
async def overview(user: UserDep, db: DbDep, services: ServicesDep) -> list[OverviewRow]:
    """One summary row per watchlisted symbol; a failing symbol gets an "unavailable" row."""
    symbols = await WatchlistsRepository(db).get(user.id)
    return await build_overview(services.market, services.analysis, symbols)


@router.put("/watchlist/{symbol}")
async def add_symbol(symbol: str, user: UserDep, db: DbDep, services: ServicesDep) -> WatchlistOut:
    """Add a stock the vendor knows (looked up cache-first, so repeats cost nothing)."""
    wanted = _normalise(symbol)
    await services.market.quote(wanted)  # unknown symbol: 404, nothing is saved
    repo = WatchlistsRepository(db)
    try:
        await repo.add(user.id, wanted, MAX_SYMBOLS)
    except WatchlistFullError as exc:
        raise AppError(
            409, "conflict", f"Your watchlist is full ({MAX_SYMBOLS} symbols maximum)."
        ) from exc
    return WatchlistOut(symbols=await repo.get(user.id))


@router.delete("/watchlist/{symbol}")
async def remove_symbol(symbol: str, user: UserDep, db: DbDep) -> WatchlistOut:
    repo = WatchlistsRepository(db)
    await repo.remove(user.id, _normalise(symbol))
    return WatchlistOut(symbols=await repo.get(user.id))
