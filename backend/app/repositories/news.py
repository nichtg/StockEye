"""News articles and per-symbol ingestion progress.

One document per distinct story (``dedupe_key``), shared by every symbol it mentions: re-fetching
the same headline for another symbol only adds to its ``symbols`` array.

Every document carries ``is_recap`` and ``is_low_value`` flags so Mongo can count and filter
without scanning titles in Python. A same-day near-duplicate of a kept article is not stored;
it is recorded on the kept one as ``similar`` (newest first, at most ``SIMILAR_CAP``),
``similar_keys`` (every folded dedupe key, so a re-fetch never counts twice) and
``similar_count``.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, UpdateOne

from app.db import Database, Document
from app.domain.macro import ScoredArticle, is_price_recap
from app.domain.news import LOW_VALUE_VERSION, Story, is_low_value
from app.providers.models import NewsItem

ARTICLES = "news_articles"
STATE = "news_ingest_state"
SIMILAR_CAP = 10  # entries kept per article; ``similar_count`` still counts them all

_PUNCT = re.compile(r"[^\w\s]")
_SPACES = re.compile(r"\s+")


def dedupe_key(title: str, source: str) -> str:
    """sha256 of the normalized title (lowercase, no punctuation) plus "|" and the source."""
    normalized = _SPACES.sub(" ", _PUNCT.sub("", title.lower())).strip()
    return hashlib.sha256(f"{normalized}|{source.lower()}".encode()).hexdigest()


@dataclass(frozen=True)
class ArticleText:
    id: ObjectId
    text: str  # title + ". " + summary, the input to the sentiment model


@dataclass(frozen=True)
class StoredSimilar:
    """A near-duplicate recorded on a kept article (it has no document, so no score)."""

    title: str
    url: str
    source: str
    published_at: datetime


@dataclass(frozen=True)
class RecentArticle:
    """One stored article for the News tab; ``score`` is None until the article is scored."""

    published_at: datetime
    title: str
    url: str
    source: str
    score: float | None
    dedupe_key: str  # the tiebreak that makes pagination stable when timestamps are equal
    similar: tuple[StoredSimilar, ...] = ()  # folded at ingest, newest first

    @property
    def position(self) -> tuple[datetime, str]:
        """Total-order position ``(published_at, dedupe_key)``, the paging cursor."""
        return self.published_at, self.dedupe_key


@dataclass(frozen=True)
class SentimentRecord:
    id: ObjectId
    positive: float
    negative: float
    neutral: float
    score: float
    model_version: str


@dataclass(frozen=True)
class IngestState:
    backfilled_months: set[str] = field(default_factory=set)
    last_incremental_at: datetime | None = None
    last_attempt_at: datetime | None = None
    in_progress_since: datetime | None = None
    last_error: str | None = None
    scoring_error: str | None = None


async def install_indexes(db: Database) -> None:
    await db[ARTICLES].create_index("dedupe_key", unique=True, name="dedupe_key_unique")
    await db[ARTICLES].create_index(
        [("symbols", ASCENDING), ("published_at", ASCENDING)], name="symbols_published"
    )
    # The weekly retention delete filters on date alone, for every symbol; the index above leads
    # with ``symbols`` and cannot serve it.
    await db[ARTICLES].create_index("published_at", name="published_at")
    await db[STATE].create_index("symbol", unique=True, name="symbol_unique")


# Recaps and low-value items are never shown. ``$ne: True`` also keeps documents that predate the
# flags (the startup backfill sets them); the feed's Python recap check covers those meanwhile.
SHOWABLE: Document = {"is_recap": {"$ne": True}, "is_low_value": {"$ne": True}}


def _recent_query(
    symbol: str,
    since: datetime,
    after: tuple[datetime, str] | None,
    until: datetime | None = None,
) -> Document:
    """The exact filter ``NewsRepository.recent`` runs (shared so tests can explain it).

    ``until`` is an exclusive upper bound (the end of a month filter); a cursor can never
    widen the window past it.
    """
    query: Document = {
        "symbols": symbol,
        "url": {"$regex": "^https?://"},
        "published_at": {"$gte": since},
        **SHOWABLE,
    }
    if until is not None:
        query["published_at"]["$lt"] = until
    if after is not None:
        moment, key = after
        query["published_at"]["$lte"] = moment
        query["$or"] = [{"published_at": {"$lt": moment}}, {"dedupe_key": {"$lt": key}}]
    return query


class NewsRepository:
    def __init__(self, db: Database) -> None:
        self._articles = db[ARTICLES]
        self._state = db[STATE]

    async def upsert_articles(self, symbol: str, items: list[NewsItem]) -> int:
        """Store ``items`` for ``symbol``; known stories just gain it. Returns items seen.

        New documents get the ``is_recap`` / ``is_low_value`` flags (known ones keep theirs).
        """
        if not items:
            return 0
        ops = [
            UpdateOne(
                {"dedupe_key": dedupe_key(item.title, item.source)},
                {
                    "$addToSet": {"symbols": symbol},
                    "$setOnInsert": {
                        "url": str(item.url),
                        "title": item.title,
                        "summary": item.summary,
                        "source": item.source,
                        "provider": item.provider,
                        "published_at": item.published_at,
                        "sentiment": None,
                        "model_version": None,
                        "is_recap": is_price_recap(item.title),
                        "is_low_value": is_low_value(item.title),
                        "low_value_version": LOW_VALUE_VERSION,
                    },
                },
                upsert=True,
            )
            for item in items
        ]
        await self._articles.bulk_write(ops, ordered=False)
        return len(items)

    async def stories_between(self, symbol: str, start: datetime, end: datetime) -> list[Story]:
        """Showable stories of ``symbol`` with ``start <= published_at < end``, as dedupe input.

        Recaps and low-value documents are left out: they are hidden, so a duplicate must not
        disappear behind one. Uses the ``symbols_published`` index.
        """
        cursor = self._articles.find(
            {"symbols": symbol, "published_at": {"$gte": start, "$lt": end}, **SHOWABLE},
            {"title": 1, "published_at": 1, "dedupe_key": 1},
            sort=[("published_at", ASCENDING), ("dedupe_key", ASCENDING)],  # a stable group head
        )
        return [Story(doc["dedupe_key"], doc["title"], doc["published_at"]) async for doc in cursor]

    async def existing_keys(self, symbol: str, keys: list[str]) -> set[str]:
        """Which of ``keys`` are already stored for ``symbol`` (on any day, flagged or not)."""
        if not keys:
            return set()
        cursor = self._articles.find(
            {"symbols": symbol, "dedupe_key": {"$in": keys}}, {"dedupe_key": 1}
        )
        return {doc["dedupe_key"] async for doc in cursor}

    async def unscored(self, symbol: str, limit: int) -> list[ArticleText]:
        cursor = self._articles.find(
            {"symbols": symbol, "sentiment": None},
            {"title": 1, "summary": 1},
            sort=[("published_at", ASCENDING)],
            limit=limit,
        )
        return [
            ArticleText(doc["_id"], f"{doc['title']}. {doc.get('summary') or ''}".strip())
            async for doc in cursor
        ]

    async def save_scores(self, records: list[SentimentRecord]) -> None:
        if not records:
            return
        await self._articles.bulk_write(
            [
                UpdateOne(
                    {"_id": r.id},
                    {
                        "$set": {
                            "sentiment": {
                                "positive": r.positive,
                                "negative": r.negative,
                                "neutral": r.neutral,
                                "score": r.score,
                            },
                            "model_version": r.model_version,
                        }
                    },
                )
                for r in records
            ]
        )

    async def scored(self, symbol: str, start: datetime, end: datetime) -> list[ScoredArticle]:
        """Scored articles with ``start <= published_at <= end``, oldest first."""
        cursor = self._articles.find(
            {
                "symbols": symbol,
                "sentiment": {"$ne": None},
                "published_at": {"$gte": start, "$lte": end},
                "is_low_value": {"$ne": True},  # recaps are dropped by the caller, as before
            },
            sort=[("published_at", ASCENDING)],
        )
        return [
            ScoredArticle(
                published_at=doc["published_at"],
                score=float(doc["sentiment"]["score"]),
                title=doc["title"],
                url=doc["url"],
                source=doc["source"],
            )
            async for doc in cursor
        ]

    async def recent(
        self,
        symbol: str,
        *,
        since: datetime,
        after: tuple[datetime, str] | None,
        limit: int,
        until: datetime | None = None,
    ) -> list[RecentArticle]:
        """Up to ``limit + 1`` articles, newest first (the extra row says "more exist").

        Keeps ``published_at >= since``. With ``after = (t, k)`` it keeps only rows strictly
        later in the order: older than ``t``, or at ``t`` with a smaller ``dedupe_key``. The
        order is ``published_at`` then ``dedupe_key``, both descending, so equal timestamps
        never reorder between pages. Scored and unscored articles both count; only http(s)
        links are returned. The ``symbols_published`` index serves the match; the
        ``dedupe_key`` tiebreak adds an in-memory SORT, which is fine at per-symbol volumes.
        """
        query = _recent_query(symbol, since, after, until)
        cursor = self._articles.find(
            query,
            {
                "title": 1,
                "url": 1,
                "source": 1,
                "published_at": 1,
                "sentiment": 1,
                "dedupe_key": 1,
                "similar": 1,
            },
            sort=[("published_at", DESCENDING), ("dedupe_key", DESCENDING)],
            limit=limit + 1,
        )
        return [
            RecentArticle(
                published_at=doc["published_at"],
                title=doc["title"],
                url=doc["url"],
                source=doc["source"],
                score=None if doc.get("sentiment") is None else float(doc["sentiment"]["score"]),
                dedupe_key=doc["dedupe_key"],
                similar=tuple(
                    StoredSimilar(e["title"], e["url"], e["source"], e["published_at"])
                    for e in doc.get("similar", [])
                ),
            )
            async for doc in cursor
        ]

    async def month_counts(self, symbol: str, since: datetime, tz: ZoneInfo) -> dict[str, int]:
        """Showable articles per exchange-local month (``"YYYY-MM"``) since ``since``.

        Recaps and low-value documents are not counted. No ``until``: deliberately the whole
        window, whichever month the tab shows. Until the startup flag backfill has finished,
        documents without the flags are counted, unflagged recaps included.
        """
        pipeline: list[Document] = [
            {"$match": _recent_query(symbol, since, None)},
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m",
                            "date": "$published_at",
                            "timezone": tz.key,
                        }
                    },
                    "n": {"$sum": 1},
                }
            },
        ]
        cursor = await self._articles.aggregate(pipeline)
        return {doc["_id"]: int(doc["n"]) async for doc in cursor}

    # --- ingestion state -------------------------------------------------------------------

    async def get_state(self, symbol: str) -> IngestState:
        doc: Document | None = await self._state.find_one({"symbol": symbol})
        if doc is None:
            return IngestState()
        return IngestState(
            backfilled_months=set(doc.get("backfilled_months", [])),
            last_incremental_at=doc.get("last_incremental_at"),
            last_attempt_at=doc.get("last_attempt_at"),
            in_progress_since=doc.get("in_progress_since"),
            last_error=doc.get("last_error"),
            scoring_error=doc.get("scoring_error"),
        )

    async def begin_run(self, symbol: str, now: datetime) -> None:
        await self._set(symbol, {"in_progress_since": now, "last_attempt_at": now})

    async def end_run(self, symbol: str, error: str | None) -> None:
        await self._set(symbol, {"in_progress_since": None, "last_error": error})

    async def mark_month_done(self, symbol: str, month: str) -> None:
        await self._state.update_one(
            {"symbol": symbol}, {"$addToSet": {"backfilled_months": month}}, upsert=True
        )

    async def mark_incremental(self, symbol: str, now: datetime) -> None:
        await self._set(symbol, {"last_incremental_at": now})

    async def set_scoring_error(self, symbol: str, error: str | None) -> None:
        await self._set(symbol, {"scoring_error": error})

    async def _set(self, symbol: str, values: Document) -> None:
        await self._state.update_one({"symbol": symbol}, {"$set": values}, upsert=True)
