"""The News tab's article feed, as one deep module: ``NewsFeed.page`` and nothing else public.

Cursors, price-recap filtering, paging and sentiment labels are internal. Read-only: nothing
here starts ingestion (the News tab's progress poll does that).
"""

import asyncio
import base64
import binascii
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.domain.macro import bucket_of, is_price_recap
from app.repositories.news import RecentArticle
from app.services.errors import AppError
from app.services.reports import NewsArticleOut, NewsArticlesOut, SentimentLabel
from app.services.status import DataStatus

NEWS_TAB_DAYS = 182  # about six months
DEFAULT_LIMIT = 30
MAX_LIMIT = 50
# Recap headlines are dropped after fetching, so a page may need several reads. Five rounds of
# at most ``MAX_LIMIT + 1`` rows bounds one request at 255 rows; if a page is still short after
# that (a stream of mostly recaps), it is returned as is with a cursor to continue from, so a
# page can be short or even empty while ``next_cursor`` is set.
MAX_ROUNDS = 5
_EARLIEST_CURSOR = datetime(2000, 1, 1, tzinfo=UTC)
_CURSOR_FUTURE_SLACK = timedelta(days=1)

type _Position = tuple[datetime, str]  # (published_at, dedupe_key): a total order, no ties


class _ArticleSource(Protocol):
    async def recent(
        self, symbol: str, *, since: datetime, after: _Position | None, limit: int
    ) -> list[RecentArticle]: ...


def _bad_cursor() -> AppError:
    return AppError(422, "validation_error", "The page cursor is not valid.")


def _encode_cursor(position: _Position) -> str:
    """URL-safe base64 of ``{"t": <iso>, "k": <key>}``; opaque to clients."""
    raw = json.dumps({"t": position[0].isoformat(), "k": position[1]}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str, now: datetime) -> _Position:
    """Inverse of ``_encode_cursor``. Raises a 422 ``AppError`` for anything else.

    The time must be timezone-aware and between 2000-01-01 and one day past ``now``: extreme
    values would otherwise overflow BSON encoding and surface as a 500.
    """
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        data = json.loads(raw)
        if not isinstance(data, dict) or set(data) != {"t", "k"}:
            raise _bad_cursor()
        stamp, key = data["t"], data["k"]
        if not isinstance(stamp, str) or not isinstance(key, str) or not key:
            raise _bad_cursor()
        moment = datetime.fromisoformat(stamp)
        if moment.tzinfo is None:
            raise _bad_cursor()
        moment = moment.astimezone(UTC)
    except (binascii.Error, ValueError, KeyError, TypeError, OverflowError) as exc:
        raise _bad_cursor() from exc
    if not _EARLIEST_CURSOR <= moment <= now + _CURSOR_FUTURE_SLACK:
        raise _bad_cursor()
    return moment, key


def _sentiment_label(score: float | None) -> SentimentLabel:
    """Macro-tab buckets (the same +-0.3 thresholds); ``not_scored`` before scoring."""
    return "not_scored" if score is None else bucket_of(score)


def _article_out(article: RecentArticle) -> NewsArticleOut:
    return NewsArticleOut(
        published_at=article.published_at,
        title=article.title,
        url=article.url,
        source=article.source,
        sentiment_label=_sentiment_label(article.score),
        sentiment=article.score,
    )


@dataclass(frozen=True)
class _Page:
    articles: list[RecentArticle]
    next_position: _Position | None  # None when the window is exhausted


async def _collect_page(
    fetch: Callable[[_Position | None], Awaitable[list[RecentArticle]]],
    limit: int,
    start: _Position | None,
) -> _Page:
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
                return _Page(kept, kept[-1].position)
            kept.append(row)
        if len(rows) <= limit:
            return _Page(kept, None)
        position = rows[-1].position
    if len(kept) == limit:  # full, and the source may still hold more
        return _Page(kept, kept[-1].position)
    return _Page(kept, position)


class NewsFeed:
    """Pages of stored news for the News tab: the last ``NEWS_TAB_DAYS`` days, newest first."""

    def __init__(
        self,
        repo: _ArticleSource,
        clock: Callable[[], datetime],
        status: Callable[[str], Awaitable[DataStatus]],
    ) -> None:
        self._repo = repo
        self._clock = clock
        self._status = status

    async def page(
        self, symbol: str, before: str | None = None, limit: int = DEFAULT_LIMIT
    ) -> NewsArticlesOut:
        """One page without price-recap headlines (so it matches the Macro tab).

        ``before`` is a cursor from an earlier page; a malformed one, or a ``limit`` outside
        ``1..MAX_LIMIT``, raises a 422 ``AppError``. Keep paging until ``next_cursor`` is None.
        """
        if not 1 <= limit <= MAX_LIMIT:
            raise AppError(422, "validation_error", f"limit must be between 1 and {MAX_LIMIT}.")
        now = self._clock()
        start = _decode_cursor(before, now) if before is not None else None
        since = now - timedelta(days=NEWS_TAB_DAYS)

        async def fetch(position: _Position | None) -> list[RecentArticle]:
            return await self._repo.recent(symbol, since=since, after=position, limit=limit)

        page, status = await asyncio.gather(
            _collect_page(fetch, limit, start), self._status(symbol)
        )
        return NewsArticlesOut(
            articles=[_article_out(a) for a in page.articles],
            next_cursor=None if page.next_position is None else _encode_cursor(page.next_position),
            since=since,
            status=status,
        )
