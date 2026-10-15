"""The News tab's article feed, as one deep module: ``NewsFeed.page`` and nothing else public.

Cursors, price-recap filtering, paging and sentiment labels are internal. Read-only: nothing
here starts ingestion (the News tab's progress poll does that).
"""

import asyncio
import base64
import binascii
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from app.domain.macro import bucket_of, is_price_recap
from app.domain.news import InvalidMonthError, cluster_stories, month_window
from app.repositories.news import RecentArticle
from app.services.calendars import exchange_tz
from app.services.errors import AppError
from app.services.news import core_name
from app.services.reports import (
    NewsArticleOut,
    NewsArticlesOut,
    NewsMonthOut,
    SentimentLabel,
    SimilarArticleOut,
)
from app.services.status import DataStatus

NEWS_TAB_DAYS = 182  # about six months
DEFAULT_LIMIT = 30
MAX_LIMIT = 50
# Recap headlines are dropped after fetching, so a page may need several reads. Five rounds of
# at most ``MAX_LIMIT + 1`` rows bounds one request at 255 rows; if a page is still short after
# that (a stream of mostly recaps), it is returned as is with a cursor to continue from, so a
# page can be short or even empty while ``next_cursor`` is set.
MAX_ROUNDS = 5
MONTHS_TTL = timedelta(minutes=5)
_EARLIEST_CURSOR = datetime(2000, 1, 1, tzinfo=UTC)
_CURSOR_FUTURE_SLACK = timedelta(days=1)

type _Position = tuple[datetime, str]  # (published_at, dedupe_key): a total order, no ties


class _ArticleSource(Protocol):
    async def recent(
        self,
        symbol: str,
        *,
        since: datetime,
        after: _Position | None,
        limit: int,
        until: datetime | None = None,
    ) -> list[RecentArticle]: ...

    async def window_titles(self, symbol: str, since: datetime) -> list[tuple[datetime, str]]: ...


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


_MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _bad_month() -> AppError:
    return AppError(
        422, "validation_error", f"month must be YYYY-MM within the last {NEWS_TAB_DAYS} days."
    )


def _month_key(moment: datetime, tz: ZoneInfo) -> str:
    local = moment.astimezone(tz)
    return f"{local.year:04d}-{local.month:02d}"


def _month_counts(titles: list[tuple[datetime, str]], tz: ZoneInfo) -> list[NewsMonthOut]:
    """Non-recap articles per exchange-local month, newest month first; empty months omitted."""
    counts: dict[str, int] = {}
    for published_at, title in titles:
        if not is_price_recap(title):
            key = _month_key(published_at, tz)
            counts[key] = counts.get(key, 0) + 1
    return [
        NewsMonthOut(
            month=key, label=f"{_MONTH_NAMES[int(key[5:]) - 1]} {key[:4]}", count=counts[key]
        )
        for key in sorted(counts, reverse=True)
    ]


def _ignore_tokens(symbol: str, company_name: str | None) -> set[str]:
    """Words every headline about the symbol shares: ticker parts and the company's core name.

    ("D05.SI" gives d05 and si; "Rocket Lab Holdings, Inc." gives rocket and lab.)
    """
    text = symbol if company_name is None else f"{symbol} {core_name(company_name)}"
    return {part for part in re.split(r"[^a-z0-9]+", text.lower()) if part}


def _group_out(members: list[RecentArticle]) -> NewsArticleOut:
    """One item for a group (newest first): the main article plus its look-alikes.

    The sentiment is the mean of the members that have a score; none scored means
    ``not_scored``.
    """
    main = members[0]
    scores = [m.score for m in members if m.score is not None]
    mean = sum(scores) / len(scores) if scores else None
    return NewsArticleOut(
        published_at=main.published_at,
        title=main.title,
        url=main.url,
        source=main.source,
        sentiment_label=_sentiment_label(mean),
        sentiment=mean,
        similar=[
            SimilarArticleOut(
                title=m.title, url=m.url, source=m.source, published_at=m.published_at
            )
            for m in members[1:]
        ],
    )


def _grouped(articles: list[RecentArticle], ignore: set[str], tz: ZoneInfo) -> list[NewsArticleOut]:
    """Collapse same-exchange-day near-duplicate stories within one page (newest first).

    Grouping only sees the page it is given, so a story can split across a page edge; that
    is accepted rather than paying for look-ahead.
    """
    items = [(a.published_at.astimezone(tz).date(), a.title) for a in articles]
    return [_group_out([articles[i] for i in g]) for g in cluster_stories(items, ignore)]


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
        company_name: Callable[[str], Awaitable[str]] | None = None,
    ) -> None:
        self._repo = repo
        self._clock = clock
        self._status = status
        self._company_name = company_name
        # (symbol, window day) -> (expires_at, counts). A client can omit the cursor on every
        # call, so the whole-window scan is cached rather than repeated.
        self._months: dict[tuple[str, date], tuple[datetime, list[NewsMonthOut]]] = {}

    async def page(
        self,
        symbol: str,
        before: str | None = None,
        limit: int = DEFAULT_LIMIT,
        month: str | None = None,
    ) -> NewsArticlesOut:
        """One page without price-recap headlines (so it matches the Macro tab).

        ``before`` is a cursor from an earlier page; a malformed one, or a ``limit`` outside
        ``1..MAX_LIMIT``, raises a 422 ``AppError``. Keep paging until ``next_cursor`` is None.

        ``month`` ("YYYY-MM", exchange-local) restricts the feed to that month clipped to the
        window; a malformed month or one wholly outside the window is a 422. Paging inside a
        month uses the same cursor, and the month bound holds whatever the cursor says.
        ``months`` (counts over the whole window) is returned on the first page only.
        ``limit`` counts articles fetched, not groups: near-duplicate same-day stories are
        grouped within the page.
        """
        if not 1 <= limit <= MAX_LIMIT:
            raise AppError(422, "validation_error", f"limit must be between 1 and {MAX_LIMIT}.")
        now = self._clock()
        start = _decode_cursor(before, now) if before is not None else None
        since = now - timedelta(days=NEWS_TAB_DAYS)
        tz = exchange_tz(symbol)
        until: datetime | None = None
        window_start = since
        if month is not None:
            try:
                window_start, until = month_window(month, tz, now, since)
            except InvalidMonthError as exc:
                raise _bad_month() from exc

        async def fetch(position: _Position | None) -> list[RecentArticle]:
            return await self._repo.recent(
                symbol, since=window_start, after=position, limit=limit, until=until
            )

        async def months() -> list[NewsMonthOut] | None:
            if before is not None:
                return None
            return await self._month_counts(symbol, now, since, tz)

        async def ignore() -> set[str]:
            name = None if self._company_name is None else await self._company_name(symbol)
            return _ignore_tokens(symbol, name)

        page, status, month_counts, skip = await asyncio.gather(
            _collect_page(fetch, limit, start), self._status(symbol), months(), ignore()
        )
        return NewsArticlesOut(
            articles=_grouped(page.articles, skip, tz),
            next_cursor=None if page.next_position is None else _encode_cursor(page.next_position),
            since=since,
            status=status,
            months=month_counts,
        )

    async def _month_counts(
        self, symbol: str, now: datetime, since: datetime, tz: ZoneInfo
    ) -> list[NewsMonthOut]:
        """Per-month counts, cached for ``MONTHS_TTL`` per symbol and (UTC) window day."""
        key = (symbol, now.date())
        cached = self._months.get(key)
        if cached is not None and now < cached[0]:
            return cached[1]
        counts = _month_counts(await self._repo.window_titles(symbol, since), tz)
        self._months = {k: v for k, v in self._months.items() if now < v[0]}  # drop stale
        self._months[key] = (now + MONTHS_TTL, counts)
        return counts
