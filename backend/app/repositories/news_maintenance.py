"""Writes over the news collection that are not plain ingest: similar-story records, flag backfill,
retroactive near-duplicate folding and date retention.

Same collection and document shape as ``repositories.news`` (see its docstring); kept apart so
each module stays small.
"""

from dataclasses import dataclass, field
from datetime import datetime

from pymongo import ASCENDING, UpdateOne

from app.db import Database, Document
from app.domain.macro import is_price_recap
from app.domain.news import is_low_value
from app.providers.models import NewsItem
from app.repositories.news import ARTICLES, SHOWABLE, SIMILAR_CAP, STATE, dedupe_key

FLAG_BATCH = 500


@dataclass(frozen=True)
class SimilarEntry:
    """A story to record on a kept article; ``key`` is its dedupe key."""

    key: str
    title: str
    url: str
    source: str
    published_at: datetime


def similar_entry(item: NewsItem) -> SimilarEntry:
    return SimilarEntry(
        dedupe_key(item.title, item.source),
        item.title,
        str(item.url),
        item.source,
        item.published_at,
    )


@dataclass(frozen=True)
class StoredArticle:
    """A stored article as the retroactive dedupe sees it, with the entries it already holds."""

    key: str
    title: str
    url: str
    source: str
    published_at: datetime
    similar: list[SimilarEntry] = field(default_factory=list)

    def as_entry(self) -> SimilarEntry:
        return SimilarEntry(self.key, self.title, self.url, self.source, self.published_at)


class NewsMaintenanceRepository:
    def __init__(self, db: Database) -> None:
        self._articles = db[ARTICLES]
        self._state = db[STATE]

    async def add_similar(self, folds: dict[str, list[SimilarEntry]]) -> int:
        """Record each entry on its kept article (``folds`` maps kept key to entries).

        Returns how many entries were new. One atomic update per entry, guarded by
        ``similar_keys``, so it is idempotent (a re-fetch, or a retry after a crash, never
        counts twice, also after the capped ``similar`` list dropped the entry) and safe when
        two symbols fold into one shared article at the same moment. ``similar`` stays newest
        first and capped; ``similar_count`` counts every entry. A kept article deleted in the
        meantime is simply skipped.
        """
        ops = [
            UpdateOne(
                {"dedupe_key": main, "similar_keys": {"$ne": entry.key}},
                {
                    "$push": {
                        "similar": {
                            "$each": [
                                {
                                    "title": entry.title,
                                    "url": entry.url,
                                    "source": entry.source,
                                    "published_at": entry.published_at,
                                }
                            ],
                            "$sort": {"published_at": -1},
                            "$slice": SIMILAR_CAP,
                        }
                    },
                    "$addToSet": {"similar_keys": entry.key},
                    "$inc": {"similar_count": 1},
                },
            )
            for main, entries in folds.items()
            for entry in entries
        ]
        if not ops:
            return 0
        result = await self._articles.bulk_write(ops, ordered=False)
        return result.modified_count

    async def backfill_flags(self) -> int:
        """Set ``is_recap`` / ``is_low_value`` on documents that lack either; returns the count.

        Idempotent: updated documents leave the filter, so each pass takes the next batch and
        a second run finds nothing. Documents flagged low-value stay stored.
        """
        missing: Document = {
            "$or": [{"is_recap": {"$exists": False}}, {"is_low_value": {"$exists": False}}]
        }
        done = 0
        while True:
            docs = [
                doc async for doc in self._articles.find(missing, {"title": 1}, limit=FLAG_BATCH)
            ]
            if not docs:
                return done
            await self._articles.bulk_write(
                [
                    UpdateOne(
                        {"_id": doc["_id"]},
                        {
                            "$set": {
                                "is_recap": is_price_recap(doc["title"]),
                                "is_low_value": is_low_value(doc["title"]),
                            }
                        },
                    )
                    for doc in docs
                ],
                ordered=False,
            )
            done += len(docs)

    async def delete_published_before(self, cutoff: datetime) -> int:
        """Delete every article with ``published_at < cutoff``, whatever its symbols."""
        result = await self._articles.delete_many({"published_at": {"$lt": cutoff}})
        return result.deleted_count

    # --- retroactive near-duplicate folding ------------------------------------------------

    async def symbols_to_dedupe(self, version: int) -> list[str]:
        """Symbols with stored articles whose state lacks ``dedupe_version >= version``."""
        done = {
            doc["symbol"]
            async for doc in self._state.find({"dedupe_version": {"$gte": version}}, {"symbol": 1})
        }
        symbols: list[str] = await self._articles.distinct("symbols")
        return sorted(s for s in symbols if s not in done)

    async def showable_articles(self, symbol: str) -> list[StoredArticle]:
        """Every showable stored article of ``symbol``, oldest first (ties by key)."""
        cursor = self._articles.find(
            {"symbols": symbol, **SHOWABLE},
            {"title": 1, "url": 1, "source": 1, "published_at": 1, "dedupe_key": 1, "similar": 1},
            sort=[("published_at", ASCENDING), ("dedupe_key", ASCENDING)],
        )
        return [
            StoredArticle(
                doc["dedupe_key"],
                doc["title"],
                doc["url"],
                doc["source"],
                doc["published_at"],
                [
                    SimilarEntry(
                        dedupe_key(e["title"], e["source"]),
                        e["title"],
                        e["url"],
                        e["source"],
                        e["published_at"],
                    )
                    for e in doc.get("similar", [])
                ],
            )
            async for doc in cursor
        ]

    async def unlink_symbol(self, symbol: str, keys: list[str]) -> int:
        """Remove ``symbol`` from the articles ``keys``; delete those left with no symbol.

        Returns how many documents were deleted. A story shared with another symbol stays.
        """
        if not keys:
            return 0
        await self._articles.update_many(
            {"dedupe_key": {"$in": keys}}, {"$pull": {"symbols": symbol}}
        )
        result = await self._articles.delete_many(
            {"dedupe_key": {"$in": keys}, "symbols": {"$size": 0}}
        )
        return result.deleted_count

    async def mark_deduped(self, symbol: str, version: int) -> None:
        await self._state.update_one(
            {"symbol": symbol}, {"$set": {"dedupe_version": version}}, upsert=True
        )
