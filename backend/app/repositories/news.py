"""News articles and per-symbol ingestion progress.

One document per distinct story (``dedupe_key``), shared by every symbol it mentions: re-fetching
the same headline for another symbol only adds to its ``symbols`` array.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime

from bson import ObjectId
from pymongo import ASCENDING, UpdateOne

from app.db import Database, Document
from app.domain.macro import ScoredArticle
from app.providers.models import NewsItem

ARTICLES = "news_articles"
STATE = "news_ingest_state"

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
    await db[STATE].create_index("symbol", unique=True, name="symbol_unique")


class NewsRepository:
    def __init__(self, db: Database) -> None:
        self._articles = db[ARTICLES]
        self._state = db[STATE]

    async def upsert_articles(self, symbol: str, items: list[NewsItem]) -> int:
        """Store ``items`` for ``symbol``; known stories just gain it. Returns items seen."""
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
                    },
                },
                upsert=True,
            )
            for item in items
        ]
        await self._articles.bulk_write(ops, ordered=False)
        return len(items)

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
