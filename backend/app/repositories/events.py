"""Corporate events (earnings, dividends, splits), keyed by (symbol, kind, date)."""

from dataclasses import dataclass
from datetime import UTC, date, datetime

from pymongo import ASCENDING, ReturnDocument, UpdateOne

from app.db import Database, Document
from app.providers.models import CorporateEvent

EVENTS = "corporate_events"
STATE = "corporate_events_state"


@dataclass(frozen=True)
class EventsFetchState:
    last_fetched_at: datetime
    covered_start: date
    covered_end: date


async def install_indexes(db: Database) -> None:
    await db[EVENTS].create_index(
        [("symbol", ASCENDING), ("kind", ASCENDING), ("date", ASCENDING)],
        unique=True,
        name="symbol_kind_date",
    )
    await db[STATE].create_index("symbol", unique=True, name="symbol_unique")


class EventsRepository:
    def __init__(self, db: Database) -> None:
        self._events = db[EVENTS]
        self._state = db[STATE]

    async def upsert_many(
        self,
        symbol: str,
        events: list[CorporateEvent],
        *,
        start: date,
        end: date,
        fetched_at: datetime,
    ) -> EventsFetchState:
        """Upsert ``events``, record [start, end] as fetched at ``fetched_at``, return the state."""
        if events:
            await self._events.bulk_write(
                [
                    UpdateOne(
                        {"symbol": symbol, "kind": e.kind, "date": e.date.isoformat()},
                        {"$set": {"label": e.label, "value": e.value}},
                        upsert=True,
                    )
                    for e in events
                ]
            )
        # One atomic upsert; ISO dates compare correctly as strings, so coverage only widens.
        doc = await self._state.find_one_and_update(
            {"symbol": symbol},
            {
                "$set": {"last_fetched_at": fetched_at},
                "$min": {"covered_start": start.isoformat()},
                "$max": {"covered_end": end.isoformat()},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:  # an upsert always yields the document
            raise RuntimeError("fetch-state upsert returned nothing")
        return _to_state(doc)

    async def get_range(self, symbol: str, start: date, end: date) -> list[CorporateEvent]:
        """Events with ``start <= date <= end``, oldest first (ISO dates sort correctly)."""
        cursor = self._events.find(
            {"symbol": symbol, "date": {"$gte": start.isoformat(), "$lte": end.isoformat()}},
            sort=[("date", ASCENDING), ("kind", ASCENDING)],
        )
        return [
            CorporateEvent(
                kind=doc["kind"],
                date=date.fromisoformat(doc["date"]),
                label=doc["label"],
                value=doc.get("value"),
            )
            async for doc in cursor
        ]

    async def get_state(self, symbol: str) -> EventsFetchState | None:
        doc = await self._state.find_one({"symbol": symbol})
        return None if doc is None else _to_state(doc)


def _to_state(doc: Document) -> EventsFetchState:
    fetched: datetime = doc["last_fetched_at"]
    return EventsFetchState(
        fetched.astimezone(UTC),
        date.fromisoformat(doc["covered_start"]),
        date.fromisoformat(doc["covered_end"]),
    )
