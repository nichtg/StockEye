"""The News tab's article feed: opaque cursors, recap filtering and sentiment labels.

Pure functions plus one paging loop over a repository callable, so the paging rules are
testable without a database. Read-only: nothing here starts ingestion.
"""

import base64
import binascii
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from app.domain.macro import bucket_of, is_price_recap
from app.repositories.news import RecentArticle
from app.services.errors import AppError
from app.services.reports import NewsArticleOut, SentimentLabel

NEWS_TAB_DAYS = 182  # about six months
DEFAULT_LIMIT = 30
MAX_LIMIT = 50
# Recap headlines are dropped after fetching, so a page may need several reads. Five rounds of
# at most ``MAX_LIMIT + 1`` rows bounds one request at 255 rows; if a page is still short after
# that (a stream of mostly recaps), it is returned as is with a cursor to continue from.
MAX_ROUNDS = 5

type Position = tuple[datetime, str]  # (published_at, dedupe_key): a total order, no ties
type FetchBatch = Callable[[Position | None], Awaitable[list[RecentArticle]]]


@dataclass(frozen=True)
class FeedPage:
    articles: list[RecentArticle]
    next_position: Position | None  # None when the window is exhausted


def _bad_cursor() -> AppError:
    return AppError(422, "validation_error", "The page cursor is not valid.")


def encode_cursor(position: Position) -> str:
    """URL-safe base64 of ``{"t": <iso>, "k": <key>}``; opaque to clients."""
    raw = json.dumps({"t": position[0].isoformat(), "k": position[1]}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> Position:
    """Inverse of ``encode_cursor``. Raises a 422 ``AppError`` for anything else."""
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        data = json.loads(raw)
        if not isinstance(data, dict) or set(data) != {"t", "k"}:
            raise _bad_cursor()
        stamp, key = data["t"], data["k"]
        if not isinstance(stamp, str) or not isinstance(key, str) or not key:
            raise _bad_cursor()
        moment = datetime.fromisoformat(stamp)
    except (binascii.Error, ValueError, KeyError, TypeError) as exc:
        raise _bad_cursor() from exc
    if moment.tzinfo is None:
        raise _bad_cursor()
    return moment, key


def sentiment_label(score: float | None) -> SentimentLabel:
    """Macro-tab buckets (the same +-0.3 thresholds); ``not_scored`` before scoring."""
    return "not_scored" if score is None else bucket_of(score)


def article_out(article: RecentArticle) -> NewsArticleOut:
    return NewsArticleOut(
        published_at=article.published_at,
        title=article.title,
        url=article.url,
        source=article.source,
        sentiment_label=sentiment_label(article.score),
        sentiment=article.score,
    )


async def collect_page(fetch: FetchBatch, limit: int, start: Position | None) -> FeedPage:
    """Up to ``limit`` non-recap articles after ``start``, newest first.

    ``fetch(position)`` returns up to ``limit + 1`` rows strictly after ``position``. A row is
    never skipped or repeated: the next cursor is the last article returned, or, if the page
    came up short because of the round bound, the last row scanned.
    """
    kept: list[RecentArticle] = []
    position = start
    for _ in range(MAX_ROUNDS):
        rows = await fetch(position)
        for row in rows:
            if is_price_recap(row.title):
                continue
            if len(kept) == limit:
                return FeedPage(kept, (kept[-1].published_at, kept[-1].dedupe_key))
            kept.append(row)
        if len(rows) <= limit:
            return FeedPage(kept, None)
        position = (rows[-1].published_at, rows[-1].dedupe_key)
    if len(kept) == limit:  # full, and the source may still hold more
        return FeedPage(kept, (kept[-1].published_at, kept[-1].dedupe_key))
    return FeedPage(kept, position)
