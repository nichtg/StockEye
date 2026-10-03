"""Price bars in a MongoDB time-series collection, plus small per-(symbol, interval) fetch state.

Time-series collections do not support upserts, so a refresh inserts the fetched bars and then
deletes whatever else was stored in that time range. The fetch-state document records what
range has been fetched and when, which lets the service decide if the cache is good enough.
"""

from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime

from pymongo import ASCENDING, ReturnDocument
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
    ) -> FetchState:
        """Replace stored bars in [start, end] with ``bars``, record the fetch, return its state.

        Insert first, then delete the old in-range bars: a crash in between leaves duplicates
        (which readers de-duplicate) rather than a hole in the saved history.
        """
        series = {"meta.symbol": symbol, "meta.interval": interval}
        in_range = {**series, "ts": {"$gte": start, "$lte": end}}
        # Only bars that existed before this insert are deleted, so two overlapping refreshes of
        # one series can never delete each other's fresh bars.
        old_ids = [doc["_id"] async for doc in self._bars.find(in_range, {"_id": 1})]
        if bars:
            await self._bars.insert_many(
                [
                    {"ts": b.ts, "meta": {"symbol": symbol, "interval": interval}}
                    | b.model_dump(exclude={"ts"})
                    for b in bars
                ]
            )
        await self._bars.delete_many({**in_range, "_id": {"$in": old_ids}})
        # One atomic upsert: coverage only ever widens, and the newest bar only moves forward.
        newest = {"$max": {"last_bar_at": max(b.ts for b in bars)}} if bars else {}
        doc = await self._state.find_one_and_update(
            {"symbol": symbol, "interval": interval},
            {
                "$set": {"last_fetched_at": fetched_at},
                "$min": {"covered_start": start},
                **newest,
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:  # an upsert always yields the document
            raise RuntimeError("fetch-state upsert returned nothing")
        return _to_state(doc)

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
        return None if doc is None else _to_state(doc)


def _to_state(doc: Document) -> FetchState:
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
