"""News tab month filter, per-month counts and near-duplicate grouping."""

import asyncio
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.db import Database
from app.repositories.news import NewsRepository
from app.services.container import Services
from app.services.errors import AppError
from app.services.news_feed import NewsFeed
from app.services.reports import NewsArticleOut
from app.services.status import DataStatus, ok
from tests.services.fakes import CLOSED_NOW, FakeClock
from tests.services.test_news_feed import RECAP, seed

pytestmark = pytest.mark.integration

NY = ZoneInfo("America/New_York")
SGT = ZoneInfo("Asia/Singapore")
NOW = CLOSED_NOW  # 2026-10-03 12:00 UTC; the window opens 2026-04-04 12:00 UTC


def _titles(page_articles: list[NewsArticleOut]) -> list[str]:
    return [a.title for a in page_articles]


async def test_month_window_uses_exchange_local_boundaries(
    db: Database, services: Services
) -> None:
    # 23:30 New York on 30 Sep is already 1 Oct in UTC, but still September for a US stock.
    await seed(db, "AAPL", "late september", datetime(2026, 9, 30, 23, 30, tzinfo=NY))
    await seed(db, "AAPL", "early october", datetime(2026, 10, 1, 0, 30, tzinfo=NY))

    sept = await services.news_feed.page("AAPL", month="2026-09")
    octo = await services.news_feed.page("AAPL", month="2026-10")

    assert _titles(sept.articles) == ["late september"]
    assert _titles(octo.articles) == ["early october"]


async def test_month_window_for_sgx_uses_singapore_time(db: Database, services: Services) -> None:
    # 00:30 SGT on 1 Oct is still 30 Sep in UTC.
    await seed(db, "D05.SI", "sgx october", datetime(2026, 10, 1, 0, 30, tzinfo=SGT))
    await seed(db, "D05.SI", "sgx september", datetime(2026, 9, 30, 23, 30, tzinfo=SGT))

    octo = await services.news_feed.page("D05.SI", month="2026-10")

    assert _titles(octo.articles) == ["sgx october"]


async def test_month_clipped_to_window_start(db: Database, services: Services) -> None:
    await seed(db, "AAPL", "before window", NOW - timedelta(days=182, seconds=1))
    await seed(db, "AAPL", "inside april", NOW - timedelta(days=182))

    april = await services.news_feed.page("AAPL", month="2026-04")

    assert _titles(april.articles) == ["inside april"]


@pytest.mark.parametrize(
    "month", ["2026-9", "2026-13", "2026-00", "26-10", "abc", "2026/10", "2026-10-01", "0000-01"]
)
async def test_month_malformed_is_422(services: Services, month: str) -> None:
    with pytest.raises(AppError) as err:
        await services.news_feed.page("AAPL", month=month)

    assert err.value.status == 422


@pytest.mark.parametrize("month", ["2026-03", "2025-10", "2026-11", "2030-01", "9999-12"])
async def test_month_outside_window_is_422(services: Services, month: str) -> None:
    with pytest.raises(AppError) as err:
        await services.news_feed.page("AAPL", month=month)

    assert err.value.status == 422


async def test_month_paging_is_stable_and_bounded_by_the_month(
    db: Database, services: Services
) -> None:
    for day in range(1, 8):
        await seed(db, "AAPL", f"september story {day}", datetime(2026, 9, day, 15, tzinfo=UTC))
    await seed(db, "AAPL", "october story", datetime(2026, 10, 2, 15, tzinfo=UTC))
    seen: list[str] = []
    cursor: str | None = None

    while True:
        page = await services.news_feed.page("AAPL", before=cursor, limit=3, month="2026-09")
        seen += _titles(page.articles)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert seen == [f"september story {day}" for day in range(7, 0, -1)]


async def test_cursor_from_another_month_is_still_bounded_by_the_month(
    db: Database, services: Services
) -> None:
    await seed(db, "AAPL", "october story", datetime(2026, 10, 2, 15, tzinfo=UTC))
    await seed(db, "AAPL", "september story", datetime(2026, 9, 10, 15, tzinfo=UTC))
    await seed(db, "AAPL", "august story", datetime(2026, 8, 10, 15, tzinfo=UTC))
    first = await services.news_feed.page("AAPL", limit=1)  # cursor sits at the October story

    page = await services.news_feed.page("AAPL", before=first.next_cursor, limit=5, month="2026-08")

    assert _titles(page.articles) == ["august story"]


async def test_months_counts_exclude_recaps_omit_empty_months_and_are_newest_first(
    db: Database, services: Services
) -> None:
    await seed(db, "AAPL", "oct one", datetime(2026, 10, 2, 15, tzinfo=UTC))
    await seed(db, "AAPL", RECAP, datetime(2026, 10, 1, 15, tzinfo=UTC))
    await seed(db, "AAPL", "aug one", datetime(2026, 8, 10, 15, tzinfo=UTC))
    await seed(db, "AAPL", "aug two", datetime(2026, 8, 11, 15, tzinfo=UTC))
    await seed(db, "MSFT", "msft only", datetime(2026, 7, 11, 15, tzinfo=UTC))

    page = await services.news_feed.page("AAPL")

    assert page.months is not None
    assert [(m.month, m.label, m.count) for m in page.months] == [
        ("2026-10", "Oct 2026", 1),
        ("2026-08", "Aug 2026", 2),
    ]


async def test_months_cover_the_whole_window_whatever_month_is_selected(
    db: Database, services: Services
) -> None:
    await seed(db, "AAPL", "oct one", datetime(2026, 10, 2, 15, tzinfo=UTC))
    await seed(db, "AAPL", "aug one", datetime(2026, 8, 10, 15, tzinfo=UTC))

    page = await services.news_feed.page("AAPL", month="2026-08")

    assert _titles(page.articles) == ["aug one"]
    assert page.months is not None
    assert [m.month for m in page.months] == ["2026-10", "2026-08"]


async def test_months_use_exchange_local_months(db: Database, services: Services) -> None:
    await seed(db, "AAPL", "late september", datetime(2026, 9, 30, 23, 30, tzinfo=NY))

    page = await services.news_feed.page("AAPL")

    assert page.months is not None
    assert [(m.month, m.count) for m in page.months] == [("2026-09", 1)]


async def test_months_only_on_the_first_page(db: Database, services: Services) -> None:
    for day in range(1, 4):
        await seed(db, "AAPL", f"story {day} alpha{day}", datetime(2026, 9, day, 15, tzinfo=UTC))

    first = await services.news_feed.page("AAPL", limit=1)
    second = await services.news_feed.page("AAPL", before=first.next_cursor, limit=1)

    assert first.months is not None
    assert second.months is None


async def test_page_groups_same_day_near_duplicates_with_mean_sentiment(
    db: Database, services: Services
) -> None:
    day = datetime(2026, 10, 2, 15, tzinfo=UTC)
    await seed(db, "AAPL", "Apple delays Vision Pro to 2027", day, 0.8)
    await seed(db, "AAPL", "Apple's Vision Pro delayed to 2027", day - timedelta(hours=1), -0.2)
    await seed(db, "AAPL", "Vision Pro launch pushed to 2027, Apple says", day - timedelta(hours=2))
    await seed(db, "AAPL", "Apple wins big Services contract", day - timedelta(hours=3), 0.9)

    page = await services.news_feed.page("AAPL")

    assert _titles(page.articles) == [
        "Apple delays Vision Pro to 2027",
        "Apple wins big Services contract",
    ]
    group = page.articles[0]
    assert [s.title for s in group.similar] == [
        "Apple's Vision Pro delayed to 2027",
        "Vision Pro launch pushed to 2027, Apple says",
    ]
    assert group.sentiment == pytest.approx(0.3)  # mean of the two scored members
    assert group.sentiment_label == "positive"
    assert page.articles[1].similar == []


async def test_page_group_with_no_scored_member_is_not_scored(
    db: Database, services: Services
) -> None:
    day = datetime(2026, 10, 2, 15, tzinfo=UTC)
    await seed(db, "AAPL", "Apple delays Vision Pro to 2027", day)
    await seed(db, "AAPL", "Apple's Vision Pro delayed to 2027", day - timedelta(hours=1))

    page = await services.news_feed.page("AAPL")

    assert len(page.articles) == 1
    assert page.articles[0].sentiment is None
    assert page.articles[0].sentiment_label == "not_scored"


async def test_page_does_not_group_across_exchange_local_days(
    db: Database, services: Services
) -> None:
    late = datetime(2026, 10, 2, 5, 0, tzinfo=UTC)  # 01:00 on 2 Oct in New York
    early = datetime(2026, 10, 2, 3, 0, tzinfo=UTC)  # 23:00 on 1 Oct in New York
    await seed(db, "AAPL", "Apple delays Vision Pro to 2027", late)
    await seed(db, "AAPL", "Apple's Vision Pro delayed to 2027", early)

    page = await services.news_feed.page("AAPL")

    assert len(page.articles) == 2
    assert all(a.similar == [] for a in page.articles)


async def test_months_counts_are_cached_for_five_minutes(db: Database) -> None:
    clock = FakeClock()

    async def status(_symbol: str) -> DataStatus:
        return ok()

    async def name(_symbol: str) -> str:
        return "Apple Inc."

    feed = NewsFeed(NewsRepository(db), clock, status, name)
    await seed(db, "AAPL", "oct one", datetime(2026, 10, 2, 15, tzinfo=UTC))

    first = await feed.page("AAPL")
    await seed(db, "AAPL", "oct two", datetime(2026, 10, 2, 16, tzinfo=UTC))
    cached = await feed.page("AAPL")
    clock.now += timedelta(minutes=5, seconds=1)
    fresh = await feed.page("AAPL")

    assert first.months is not None and cached.months is not None and fresh.months is not None
    assert [m.count for m in first.months] == [1]
    assert [m.count for m in cached.months] == [1]
    assert [m.count for m in fresh.months] == [2]


async def test_months_counts_are_not_cached_while_news_is_still_collecting(db: Database) -> None:
    async def status(_symbol: str) -> DataStatus:
        return DataStatus(state="partial", as_of=None, reason="collecting")

    async def name(_symbol: str) -> str:
        return "Apple Inc."

    feed = NewsFeed(NewsRepository(db), FakeClock(), status, name)
    await seed(db, "AAPL", "oct one", datetime(2026, 10, 2, 15, tzinfo=UTC))

    first = await feed.page("AAPL")
    await seed(db, "AAPL", "oct two", datetime(2026, 10, 2, 16, tzinfo=UTC))
    second = await feed.page("AAPL")  # same instant, well inside the TTL

    assert first.months is not None and second.months is not None
    assert [m.count for m in first.months] == [1]
    assert [m.count for m in second.months] == [2]


class _CountingRepo(NewsRepository):
    def __init__(self, db: Database) -> None:
        super().__init__(db)
        self.scans = 0

    async def window_titles(self, symbol: str, since: datetime) -> list[tuple[datetime, str]]:
        self.scans += 1
        await asyncio.sleep(0.05)  # keep the scan open so concurrent callers overlap
        return await super().window_titles(symbol, since)


async def test_months_cold_cache_scans_once_under_concurrency(db: Database) -> None:
    async def status(_symbol: str) -> DataStatus:
        return ok()

    async def name(_symbol: str) -> str:
        return "Apple Inc."

    repo = _CountingRepo(db)
    feed = NewsFeed(repo, FakeClock(), status, name)
    await seed(db, "AAPL", "oct one", datetime(2026, 10, 2, 15, tzinfo=UTC))

    pages = await asyncio.gather(*(feed.page("AAPL") for _ in range(5)))

    assert repo.scans == 1
    assert all(p.months is not None and [m.count for m in p.months] == [1] for p in pages)


async def test_company_name_is_looked_up_once_a_day_and_never_caches_the_ticker(
    db: Database,
) -> None:
    clock = FakeClock()
    calls: list[str] = []
    answers = iter(["AAPL", "Apple Inc.", "Apple Inc."])

    async def status(_symbol: str) -> DataStatus:
        return ok()

    async def name(symbol: str) -> str:
        calls.append(symbol)
        return next(answers)

    feed = NewsFeed(NewsRepository(db), clock, status, name)

    await feed.page("AAPL", limit=1)  # ticker fallback: not remembered
    await feed.page("AAPL", limit=1)  # real name: remembered
    await feed.page("AAPL", limit=1)
    clock.now += timedelta(hours=25)
    await feed.page("AAPL", limit=1)

    assert len(calls) == 3
