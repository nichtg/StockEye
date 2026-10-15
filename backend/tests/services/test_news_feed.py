"""The News tab feed: window, ordering, cursor paging, recap filtering, labels."""

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest

from app.db import Database
from app.repositories.news import ARTICLES, dedupe_key, install_indexes
from app.services.container import Services
from app.services.errors import AppError
from app.services.news_feed import NEWS_TAB_DAYS, decode_cursor, encode_cursor
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
        page = await services.news.recent_articles(symbol, before=cursor, limit=limit)
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

    page = await services.news.recent_articles("AAPL")

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

    page = await services.news.recent_articles("AAPL")

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
    everything = [a.title for a in (await services.news.recent_articles("AAPL")).articles]

    for limit in (1, 2, 3, 4):  # the edge falls inside the tie group for several limits
        pages = await walk(services, "AAPL", limit)
        flat = [t for page in pages for t in page]
        assert flat == everything, f"limit={limit}"
        assert all(len(p) <= limit for p in pages)


async def test_recent_articles_other_symbols_never_appear(db: Database, services: Services) -> None:
    await seed(db, "AAPL", "apple news", _ago(days=1))
    await seed(db, "MSFT", "microsoft news", _ago(days=1))
    await seed(db, "AAPL", "shared story", _ago(days=2), symbols=["AAPL", "MSFT"])

    apple = await services.news.recent_articles("AAPL")
    msft = await services.news.recent_articles("MSFT")
    nobody = await services.news.recent_articles("SPY")

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

    page = await services.news.recent_articles("AAPL")

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

    page = await services.news.recent_articles("AAPL")

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

    page = await services.news.recent_articles("AAPL", limit=2)

    assert [a.title for a in page.articles] == ["ok one", "ok two"]
    assert all(a.url.startswith("https://") for a in page.articles)


async def test_recent_articles_is_read_only_and_does_not_start_ingestion(
    services: Services,
) -> None:
    page = await services.news.recent_articles("AAPL")

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
            await services.news.recent_articles("AAPL", before=cursor)
        assert caught.value.status == 422, cursor


def test_cursor_round_trips() -> None:
    position = (datetime(2026, 9, 1, 12, 30, 15, 123000, tzinfo=UTC), "abc123")

    assert decode_cursor(encode_cursor(position)) == position


async def test_recent_query_is_served_by_the_symbols_published_index(db: Database) -> None:
    await install_indexes(db)
    for i in range(20):
        await seed(db, "AAPL", f"a{i}", _ago(hours=i))

    plan = (
        await db[ARTICLES]
        .find({"symbols": "AAPL", "published_at": {"$gte": _ago(days=182)}})
        .sort([("published_at", -1), ("dedupe_key", -1)])
        .explain()
    )

    assert "symbols_published" in json.dumps(plan, default=str)
