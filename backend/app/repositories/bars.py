"""Price bars in a MongoDB time-series collection, plus small per-(symbol, interval) fetch state.

Time-series collections do not support upserts, so a refresh deletes the fetched time range for
the symbol and interval and re-inserts it. The fetch-state document records what range has been
fetched and when, which is what lets the service decide whether the cache is good enough.
"""

from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime

from pymongo import ASCENDING
from pymongo.errors import CollectionInvalid

from app.db import Database, Document
from app.providers.models import Bar, Interval

BARS = "price_bars"
STATE = "price_fetch_state"


@dataclass(frozen=True)
class FetchState:
    last_fetched_at: datetime
    covered_start: datetime  # start of the range last requested from the provider
    last_bar_at: datetime | None  # timestamp of the newest stored bar


async def install_indexes(db: Database) -> None:
    with suppress(CollectionInvalid):  # already exists: creation is idempotent
        await db.create_collection(
            BARS,
            timeseries={"timeField": "ts", "metaField": "meta", "granularity": "hours"},
        )
    await db[BARS].create_index(
        [("meta.symbol", ASCENDING), ("meta.interval", ASCENDING), ("ts", ASCENDING)]
    )
    await db[STATE].create_index(
        [("symbol", ASCENDING), ("interval", ASCENDING)], unique=True, name="symbol_interval"
    )


class BarsRepository:
    def __init__(self, db: Database) -> None:
        self._bars = db[BARS]
        self._state = db[STATE]

    async def replace_range(
        self,
        symbol: str,
        interval: Interval,
        bars: list[Bar],
        *,
        start: datetime,
        end: datetime,
        fetched_at: datetime,
    ) -> None:
        """Replace stored bars in [start, end] with ``bars`` and record the fetch."""
        meta = {"symbol": symbol, "interval": interval}
        await self._bars.delete_many(
            {"meta.symbol": symbol, "meta.interval": interval, "ts": {"$gte": start, "$lte": end}}
        )
        if bars:
            await self._bars.insert_many(
                [
                    {
                        "ts": b.ts,
                        "meta": meta,
                        "open": b.open,
                        "high": b.high,
                        "low": b.low,
                        "close": b.close,
                        "volume": b.volume,
                    }
                    for b in bars
                ]
            )
        previous = await self.get_state(symbol, interval)
        covered = min(start, previous.covered_start) if previous else start
        newest = await self._bars.find_one(
            {"meta.symbol": symbol, "meta.interval": interval}, sort=[("ts", -1)]
        )
        await self._state.update_one(
            {"symbol": symbol, "interval": interval},
            {
                "$set": {
                    "last_fetched_at": fetched_at,
                    "covered_start": covered,
                    "last_bar_at": newest["ts"] if newest else None,
                }
            },
            upsert=True,
        )

    async def get_range(
        self, symbol: str, interval: Interval, start: datetime, end: datetime
    ) -> list[Bar]:
        """Bars with ``start <= ts <= end``, oldest first."""
        cursor = self._bars.find(
            {"meta.symbol": symbol, "meta.interval": interval, "ts": {"$gte": start, "$lte": end}},
            sort=[("ts", ASCENDING)],
        )
        return [_to_bar(doc) async for doc in cursor]

    async def get_state(self, symbol: str, interval: Interval) -> FetchState | None:
        doc = await self._state.find_one({"symbol": symbol, "interval": interval})
        if doc is None:
            return None
        return FetchState(doc["last_fetched_at"], doc["covered_start"], doc.get("last_bar_at"))


def _to_bar(doc: Document) -> Bar:
    return Bar(
        ts=doc["ts"],
        open=doc["open"],
        high=doc["high"],
        low=doc["low"],
        close=doc["close"],
        volume=doc["volume"],
    )
