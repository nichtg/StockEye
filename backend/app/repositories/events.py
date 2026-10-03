"""Corporate events (earnings, dividends, splits), keyed by (symbol, kind, date)."""

from dataclasses import dataclass
from datetime import UTC, date, datetime

from pymongo import ASCENDING, UpdateOne

from app.db import Database
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
    ) -> None:
        """Upsert ``events`` and record that [start, end] was fetched at ``fetched_at``."""
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
        previous = await self.get_state(symbol)
        covered_start = min(start, previous.covered_start) if previous else start
        covered_end = max(end, previous.covered_end) if previous else end
        await self._state.update_one(
            {"symbol": symbol},
            {
                "$set": {
                    "last_fetched_at": fetched_at,
                    "covered_start": covered_start.isoformat(),
                    "covered_end": covered_end.isoformat(),
                }
            },
            upsert=True,
        )

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
        if doc is None:
            return None
        fetched: datetime = doc["last_fetched_at"]
        return EventsFetchState(
            fetched.astimezone(UTC),
            date.fromisoformat(doc["covered_start"]),
            date.fromisoformat(doc["covered_end"]),
        )
