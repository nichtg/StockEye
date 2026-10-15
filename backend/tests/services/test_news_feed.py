"""The News tab feed: window, ordering, cursor paging, recap filtering, labels."""

import base64
import json
from datetime import datetime, timedelta

import pytest

from app.db import Database
from app.repositories.news import (
    ARTICLES,
    RecentArticle,
    _recent_query,
    dedupe_key,
    install_indexes,
)
from app.services.container import Services
from app.services.errors import AppError
from app.services.news_feed import MAX_ROUNDS, NEWS_TAB_DAYS, NewsFeed
from app.services.status import DataStatus, ok
from tests.services.fakes import CLOSED_NOW

pytestmark = pytest.mark.integration

NOW = CLOSED_NOW
RECAP = "Apple stock drops 6% after report"  # a price-move recap headline


async def seed(
    db: Database,
    symbol: str,
    title: str,
    published_at: datetime,
    score: float | None = None,
    *,
    url: str | None = None,
    symbols: list[str] | None = None,
) -> str:
    """Insert one article directly (full control of timestamp, score and url); returns its key."""
    key = dedupe_key(title, "Wire")
    await db[ARTICLES].insert_one(
        {
            "dedupe_key": key,
            "symbols": symbols or [symbol],
            "url": url or f"https://news.example.com/{key[:12]}",
            "title": title,
            "summary": None,
            "source": "Wire",
            "provider": "test",
            "published_at": published_at,
            "sentiment": None if score is None else {"score": score},
            "model_version": None if score is None else "v1",
        }
    )
    return key


async def walk(services: Services, symbol: str, limit: int) -> list[list[str]]:
    """Titles of every page, following ``next_cursor`` until it ends."""
    pages: list[list[str]] = []
    cursor: str | None = None
    while True:
        page = await services.news_feed.page(symbol, before=cursor, limit=limit)
        pages.append([a.title for a in page.articles])
        cursor = page.next_cursor
        if cursor is None:
            return pages


def _ago(**delta: float) -> datetime:
    return NOW - timedelta(**delta)


async def test_recent_articles_window_is_182_days_and_inclusive(
    db: Database, services: Services
) -> None:
    await seed(db, "AAPL", "just inside", NOW - timedelta(days=NEWS_TAB_DAYS))
    await seed(db, "AAPL", "just outside", NOW - timedelta(days=NEWS_TAB_DAYS, seconds=1))
    await seed(db, "AAPL", "fresh", _ago(hours=1))

    page = await services.news_feed.page("AAPL")

    assert NEWS_TAB_DAYS == 182
    assert [a.title for a in page.articles] == ["fresh", "just inside"]
    assert page.since == NOW - timedelta(days=182)
    assert page.next_cursor is None


async def test_recent_articles_orders_newest_first_with_key_descending_on_ties(
    db: Database, services: Services
) -> None:
    tie = _ago(days=2)
    keys = {t: await seed(db, "AAPL", t, tie) for t in ("alpha", "bravo", "charlie", "delta")}
    await seed(db, "AAPL", "newest", _ago(days=1))
    await seed(db, "AAPL", "oldest", _ago(days=3))

    page = await services.news_feed.page("AAPL")

    tied = sorted(keys, key=lambda t: keys[t], reverse=True)
    assert [a.title for a in page.articles] == ["newest", *tied, "oldest"]


async def test_recent_articles_pages_are_stable_across_a_tie_at_the_page_edge(
    db: Database, services: Services
) -> None:
    await seed(db, "AAPL", "newest", _ago(days=1))
    tie = _ago(days=2)
    for title in ("t1", "t2", "t3", "t4", "t5"):
        await seed(db, "AAPL", title, tie)
    await seed(db, "AAPL", "oldest", _ago(days=3))
    everything = [a.title for a in (await services.news_feed.page("AAPL")).articles]

    for limit in (1, 2, 3, 4):  # the edge falls inside the tie group for several limits
        pages = await walk(services, "AAPL", limit)
        flat = [t for page in pages for t in page]
        assert flat == everything, f"limit={limit}"
        assert all(len(p) <= limit for p in pages)


async def test_recent_articles_other_symbols_never_appear(db: Database, services: Services) -> None:
    await seed(db, "AAPL", "apple news", _ago(days=1))
    await seed(db, "MSFT", "microsoft news", _ago(days=1))
    await seed(db, "AAPL", "shared story", _ago(days=2), symbols=["AAPL", "MSFT"])

    apple = await services.news_feed.page("AAPL")
    msft = await services.news_feed.page("MSFT")
    nobody = await services.news_feed.page("SPY")

    assert [a.title for a in apple.articles] == ["apple news", "shared story"]
    assert [a.title for a in msft.articles] == ["microsoft news", "shared story"]
    assert nobody.articles == []


async def test_recent_articles_excludes_recaps_and_still_fills_the_page(
    db: Database, services: Services
) -> None:
    for i in range(6):  # six recaps sit between the newest articles and the rest
        await seed(db, "AAPL", f"{RECAP} {i}", _ago(hours=1 + i))
    for i in range(5):
        await seed(db, "AAPL", f"Apple launches product {i}", _ago(days=1 + i))

    pages = await walk(services, "AAPL", 2)

    assert [len(p) for p in pages] == [2, 2, 1]
    flat = [t for p in pages for t in p]
    assert flat == [f"Apple launches product {i}" for i in range(5)]


async def test_recent_articles_all_recaps_returns_empty_page_without_cursor(
    db: Database, services: Services
) -> None:
    for i in range(3):
        await seed(db, "AAPL", f"{RECAP} {i}", _ago(hours=1 + i))

    page = await services.news_feed.page("AAPL")

    assert page.articles == []
    assert page.next_cursor is None


async def test_recent_articles_unscored_are_included_as_not_scored(
    db: Database, services: Services
) -> None:
    await seed(db, "AAPL", "pending", _ago(hours=1), None)
    await seed(db, "AAPL", "good", _ago(hours=2), 0.31)
    await seed(db, "AAPL", "bad", _ago(hours=3), -0.31)
    await seed(db, "AAPL", "edge up", _ago(hours=4), 0.3)
    await seed(db, "AAPL", "edge down", _ago(hours=5), -0.3)

    page = await services.news_feed.page("AAPL")

    labels = {a.title: (a.sentiment_label, a.sentiment) for a in page.articles}
    assert labels == {
        "pending": ("not_scored", None),
        "good": ("positive", 0.31),
        "bad": ("negative", -0.31),
        "edge up": ("neutral", 0.3),
        "edge down": ("neutral", -0.3),
    }


async def test_recent_articles_non_http_urls_are_dropped_and_do_not_shrink_pages(
    db: Database, services: Services
) -> None:
    await seed(db, "AAPL", "evil", _ago(hours=1), url="javascript:alert(1)")
    await seed(db, "AAPL", "ftp", _ago(hours=2), url="ftp://example.com/a")
    await seed(db, "AAPL", "ok one", _ago(hours=3))
    await seed(db, "AAPL", "ok two", _ago(hours=4))

    page = await services.news_feed.page("AAPL", limit=2)

    assert [a.title for a in page.articles] == ["ok one", "ok two"]
    assert all(a.url.startswith("https://") for a in page.articles)


async def test_recent_articles_is_read_only_and_does_not_start_ingestion(
    services: Services,
) -> None:
    page = await services.news_feed.page("AAPL")

    assert page.status.state == "partial"  # not collected yet
    assert not await services.news.has_history("AAPL")


async def test_recent_articles_malformed_cursor_is_422(services: Services) -> None:
    def encoded(obj: object) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode()

    bad = [
        "!!!",
        "not-a-cursor",
        base64.urlsafe_b64encode(b"not json").decode(),
        encoded([1, 2]),
        encoded({"t": "2026-10-01T00:00:00+00:00"}),
        encoded({"t": "2026-10-01T00:00:00+00:00", "k": ""}),
        encoded({"t": "2026-10-01T00:00:00+00:00", "k": 5}),
        encoded({"t": "yesterday", "k": "abc"}),
        encoded({"t": "2026-10-01T00:00:00", "k": "abc"}),  # naive time
        encoded({"t": "2026-10-01T00:00:00+00:00", "k": "abc", "x": 1}),
    ]
    for cursor in bad:
        with pytest.raises(AppError) as caught:
            await services.news_feed.page("AAPL", before=cursor)
        assert caught.value.status == 422, cursor


async def test_page_cursor_from_a_previous_page_round_trips(
    db: Database, services: Services
) -> None:
    for i in range(3):
        await seed(db, "AAPL", f"headline {i}", _ago(hours=i + 1))

    first = await services.news_feed.page("AAPL", limit=1)
    second = await services.news_feed.page("AAPL", before=first.next_cursor, limit=1)

    assert [a.title for a in second.articles] == ["headline 1"]


async def test_page_extreme_cursor_times_are_422_not_500(services: Services) -> None:
    def encoded(stamp: str) -> str:
        raw = json.dumps({"t": stamp, "k": "abc"}).encode()
        return base64.urlsafe_b64encode(raw).decode()

    for stamp in (
        "0001-01-01T00:00:00+14:00",  # overflows once converted to UTC
        "9999-12-31T23:59:59-14:00",
        "1999-12-31T23:59:59+00:00",  # before the earliest allowed
        "2026-10-05T00:00:00+00:00",  # more than a day after the clock
    ):
        with pytest.raises(AppError) as caught:
            await services.news_feed.page("AAPL", before=encoded(stamp))
        assert caught.value.status == 422, stamp


@pytest.mark.parametrize("limit", [0, -1, 51])
async def test_page_limit_outside_bounds_is_422(services: Services, limit: int) -> None:
    with pytest.raises(AppError) as caught:
        await services.news_feed.page("AAPL", limit=limit)

    assert caught.value.status == 422


@pytest.mark.parametrize("with_cursor", [False, True])
async def test_recent_query_is_served_by_the_symbols_published_index(
    db: Database, with_cursor: bool
) -> None:
    await install_indexes(db)
    for i in range(20):
        await seed(db, "AAPL", f"a{i}", _ago(hours=i))
    after = (_ago(hours=5), "m" * 64) if with_cursor else None
    query = _recent_query("AAPL", _ago(days=182), after)

    plan = await db[ARTICLES].find(query).sort([("published_at", -1), ("dedupe_key", -1)]).explain()

    winning = json.dumps(plan["queryPlanner"]["winningPlan"], default=str)
    assert "IXSCAN" in winning
    assert "symbols_published" in winning
    assert "COLLSCAN" not in winning


class _ScriptedSource:
    """An in-memory article source: newest-first rows, paged like the repository."""

    def __init__(self, titles: list[str]) -> None:
        start = NOW - timedelta(days=1)
        self.rows = [
            RecentArticle(
                published_at=start - timedelta(minutes=i),
                title=title,
                url="https://example.com/x",
                source="Wire",
                score=None,
                dedupe_key=f"{i:04d}",
            )
            for i, title in enumerate(titles)
        ]

    async def recent(
        self, symbol: str, *, since: datetime, after: tuple[datetime, str] | None, limit: int
    ) -> list[RecentArticle]:
        rows = [r for r in self.rows if after is None or r.position < after]
        return rows[: limit + 1]


async def test_page_when_recaps_exhaust_the_rounds_pages_still_return_every_article_once() -> None:
    recaps = [f"{RECAP} {i}" for i in range(20)]
    real = ["Apple news 1", "Apple news 2", "Apple news 3"]
    source = _ScriptedSource([*recaps, *real])

    async def status(_symbol: str) -> DataStatus:
        return ok()

    feed = NewsFeed(source, lambda: NOW, status)
    assert MAX_ROUNDS * 2 < 20  # limit 1 scans 2 rows a round, so the real rows are out of reach
    pages = []
    cursor: str | None = None
    while True:
        page = await feed.page("AAPL", before=cursor, limit=1)
        pages.append(page)
        cursor = page.next_cursor
        if cursor is None:
            break

    flat = [a.title for p in pages for a in p.articles]
    assert flat == real
    assert any(not p.articles and p.next_cursor is not None for p in pages)
