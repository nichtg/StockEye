"""Trimming news at ingest (near-duplicates, low-value items), the flags and the macro input."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app.db import Database
from app.domain.macro import is_price_recap
from app.domain.news import is_low_value
from app.providers.models import NewsItem, NewsQuery
from app.repositories.news import ARTICLES, SIMILAR_CAP, STATE, dedupe_key
from app.repositories.news_maintenance import (
    NewsMaintenanceRepository,
    SimilarEntry,
    similar_entry,
)
from app.services.container import Services
from app.services.news import NewsService
from app.services.news_trim import backfill_stored_news
from tests.services.fakes import CLOSED_NOW, FakeClock, FakeScorer
from tests.services.test_news_feed import seed

pytestmark = pytest.mark.integration

DAY = datetime(2026, 9, 29, 15, tzinfo=UTC)  # 11:00 in New York
FOLDABLE = "Apple delays foldable iPhone launch to 2027"
FOLDABLE_ALT = "Apple's foldable iPhone launch delayed to 2027"


def _news(title: str, when: datetime, source: str = "Wire A") -> NewsItem:
    return NewsItem.model_validate(
        {
            "url": f"https://news.example.com/{abs(hash((title, source)))}",
            "title": title,
            "summary": None,
            "source": source,
            "published_at": when,
            "provider": "scripted",
        }
    )


class _Scripted:
    """A provider that answers the incremental window with ``items`` and nothing else."""

    name = "scripted"
    exchanges = frozenset({"US", "SGX"})

    def __init__(self, items: list[NewsItem]) -> None:
        self.items = items

    async def fetch(self, query: NewsQuery) -> list[NewsItem]:
        return self.items if (query.end - query.start).days <= 31 and query.start.day != 1 else []


async def _run(db: Database, clock: FakeClock, items: list[NewsItem], symbol: str = "AAPL") -> None:
    provider = _Scripted(items)
    news = NewsService(db, provider, [provider], FakeScorer(), clock=clock)
    await news.ensure_ingested(symbol, "Apple Inc.")
    await news.wait(symbol)


async def _docs(db: Database) -> dict[str, dict[str, Any]]:
    return {doc["title"] + "|" + doc["source"]: doc async for doc in db[ARTICLES].find({})}


async def test_ingest_same_day_duplicates_in_a_batch_are_folded_into_the_earliest(
    db: Database, clock: FakeClock
) -> None:
    items = [
        _news(FOLDABLE_ALT, DAY + timedelta(hours=3), "Wire C"),
        _news(FOLDABLE, DAY, "Wire A"),
        _news("Apple delays foldable iPhone debut to 2027", DAY + timedelta(hours=1), "Wire B"),
    ]

    await _run(db, clock, items)

    docs = await _docs(db)
    assert list(docs) == [f"{FOLDABLE}|Wire A"]
    main = docs[f"{FOLDABLE}|Wire A"]
    assert main["similar_count"] == 2
    assert [s["source"] for s in main["similar"]] == ["Wire C", "Wire B"]  # newest first
    assert main["is_recap"] is False
    assert main["is_low_value"] is False


async def test_ingest_duplicate_of_an_already_stored_article_is_not_stored(
    db: Database, clock: FakeClock
) -> None:
    await _run(db, clock, [_news(FOLDABLE, DAY, "Wire A")])
    clock.now += timedelta(hours=7)  # due for a top-up

    await _run(db, clock, [_news(FOLDABLE_ALT, DAY - timedelta(hours=2), "Wire B")])

    docs = await _docs(db)
    assert len(docs) == 1  # the stored article stays main even though the new one is earlier
    main = docs[f"{FOLDABLE}|Wire A"]
    assert main["similar_count"] == 1
    assert main["similar"][0]["title"] == FOLDABLE_ALT


async def test_ingest_refetching_a_folded_duplicate_does_not_count_it_twice(
    db: Database, clock: FakeClock
) -> None:
    items = [_news(FOLDABLE, DAY), _news(FOLDABLE_ALT, DAY + timedelta(hours=1), "Wire B")]
    await _run(db, clock, items)
    clock.now += timedelta(hours=7)

    await _run(db, clock, items)  # the 30-day top-up window returns both again

    main = (await _docs(db))[f"{FOLDABLE}|Wire A"]
    assert main["similar_count"] == 1
    assert len(main["similar"]) == 1


async def test_ingest_same_story_on_another_local_day_is_stored(
    db: Database, clock: FakeClock
) -> None:
    items = [_news(FOLDABLE, DAY), _news(FOLDABLE_ALT, DAY + timedelta(days=1), "Wire B")]

    await _run(db, clock, items)

    assert len(await _docs(db)) == 2


async def test_ingest_opposed_stories_on_one_day_are_both_stored(
    db: Database, clock: FakeClock
) -> None:
    items = [
        _news("Apple shares rise on iPhone launch news today", DAY, "Wire A"),
        _news("Apple shares fall on iPhone launch news today", DAY, "Wire B"),
    ]

    await _run(db, clock, items)

    assert len(await _docs(db)) == 2


async def test_ingest_similar_list_is_capped_but_the_count_is_not(
    db: Database, clock: FakeClock
) -> None:
    items = [_news(FOLDABLE, DAY, "Wire 00")] + [
        _news(FOLDABLE, DAY + timedelta(minutes=n), f"Wire {n:02d}") for n in range(1, 14)
    ]

    await _run(db, clock, items)

    docs = await _docs(db)
    assert len(docs) == 1
    main = docs[f"{FOLDABLE}|Wire 00"]
    assert main["similar_count"] == 13
    assert len(main["similar"]) == SIMILAR_CAP
    assert main["similar"][0]["source"] == "Wire 13"  # newest first
    assert len(main["similar_keys"]) == 13


async def test_ingest_low_value_items_are_not_stored_and_recaps_are_flagged(
    db: Database, clock: FakeClock
) -> None:
    recap = "Apple stock drops 6% after report"
    assert is_price_recap(recap)
    items = [
        _news("Apple Inc. $AAPL Stake Cut by Denali Advisors LLC", DAY),
        _news("Apple stock trades at EUR 231.50 after dividend hike", DAY, "Wire B"),
        _news("Apple unveils new MacBook lineup", DAY, "Wire C"),
        _news(recap, DAY, "Wire D"),
    ]

    await _run(db, clock, items)

    docs = await _docs(db)
    assert sorted(d["title"] for d in docs.values()) == sorted(
        [recap, "Apple unveils new MacBook lineup"]
    )
    assert docs[f"{recap}|Wire D"]["is_recap"] is True
    assert docs["Apple unveils new MacBook lineup|Wire C"]["is_recap"] is False


async def test_backfill_flags_marks_old_documents_and_is_idempotent(db: Database) -> None:
    recap = "Apple stock drops 6% after report"
    await seed(db, "AAPL", recap, DAY)
    await seed(db, "AAPL", "Apple Inc. $AAPL Holdings Trimmed by Birch Capital", DAY)
    await seed(db, "AAPL", "Apple unveils new MacBook lineup", DAY)

    first = await backfill_stored_news(db)
    second = await backfill_stored_news(db)

    assert (first.flagged, second.flagged) == (3, 0)
    docs = {d["title"]: d async for d in db[ARTICLES].find({})}
    assert len(docs) == 3  # flagged documents stay stored
    assert docs[recap]["is_recap"] is True
    assert docs["Apple Inc. $AAPL Holdings Trimmed by Birch Capital"]["is_low_value"] is True
    assert docs["Apple unveils new MacBook lineup"]["is_recap"] is False
    assert docs["Apple unveils new MacBook lineup"]["is_low_value"] is False


async def test_backfill_flags_never_raises(db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(_self: NewsMaintenanceRepository) -> int:
        raise RuntimeError("mongo down")

    monkeypatch.setattr(NewsMaintenanceRepository, "backfill_flags", boom)

    summary = await backfill_stored_news(db)

    assert (summary.flagged, summary.folded) == (0, 0)


async def test_month_counts_exclude_recaps_and_low_value_and_match_the_title_scan(
    db: Database, services: Services
) -> None:
    rows = [
        ("Apple unveils new MacBook lineup", datetime(2026, 10, 2, 15, tzinfo=UTC)),
        ("Apple stock drops 6% after report", datetime(2026, 10, 2, 16, tzinfo=UTC)),
        (
            "Apple Inc. $AAPL Stake Cut by Denali Advisors LLC",
            datetime(2026, 10, 2, 17, tzinfo=UTC),
        ),
        ("Apple announces a new chip", datetime(2026, 9, 30, 23, 30, tzinfo=UTC)),
        ("Apple opens a new store", datetime(2026, 9, 10, 15, tzinfo=UTC)),
        ("Apple stock at EUR 231.50", datetime(2026, 9, 11, 15, tzinfo=UTC)),
    ]
    for title, when in rows:
        await seed(db, "AAPL", title, when)
    await NewsMaintenanceRepository(db).backfill_flags()

    page = await services.news_feed.page("AAPL")

    ny = ZoneInfo("America/New_York")
    expected: dict[str, int] = {}
    for title, when in rows:
        if not is_price_recap(title) and not is_low_value(title):
            key = when.astimezone(ny).strftime("%Y-%m")
            expected[key] = expected.get(key, 0) + 1
    assert page.months is not None
    assert {m.month: m.count for m in page.months} == expected
    assert [m.month for m in page.months] == sorted(expected, reverse=True)


async def test_feed_excludes_low_value_documents(db: Database, services: Services) -> None:
    await seed(db, "AAPL", "Apple unveils new MacBook lineup", DAY)
    await seed(db, "AAPL", "Apple Inc. $AAPL Holdings Trimmed by Birch Capital", DAY)
    await NewsMaintenanceRepository(db).backfill_flags()

    page = await services.news_feed.page("AAPL")

    assert [a.title for a in page.articles] == ["Apple unveils new MacBook lineup"]


async def test_feed_merges_stored_similar_with_read_time_groups_without_duplicates(
    db: Database, services: Services
) -> None:
    await seed(db, "AAPL", FOLDABLE, DAY)
    await seed(db, "AAPL", FOLDABLE_ALT, DAY - timedelta(hours=1))  # read-time look-alike
    extra = [
        {"title": "Apple pushes foldable iPhone to 2027", "source": "Wire X", "hours": -3},
        {"title": "Foldable iPhone launch delayed by Apple", "source": "Wire Y", "hours": -2},
    ]
    similar = [
        {
            "title": e["title"],
            "url": f"https://news.example.com/{e['source'][-1]}",
            "source": e["source"],
            "published_at": DAY + timedelta(hours=e["hours"]),
        }
        for e in extra
    ]
    # Both stored articles remember Wire X; the main one also remembers Wire Y.
    await db[ARTICLES].update_one(
        {"dedupe_key": dedupe_key(FOLDABLE, "Wire")}, {"$set": {"similar": similar}}
    )
    await db[ARTICLES].update_one(
        {"dedupe_key": dedupe_key(FOLDABLE_ALT, "Wire")}, {"$set": {"similar": similar[:1]}}
    )

    page = await services.news_feed.page("AAPL")

    assert len(page.articles) == 1
    group = page.articles[0]
    assert group.title == FOLDABLE
    assert [s.title for s in group.similar] == [
        FOLDABLE_ALT,
        "Foldable iPhone launch delayed by Apple",
        "Apple pushes foldable iPhone to 2027",
    ]


async def test_group_sentiment_is_the_mean_of_scored_stored_members_only(
    db: Database, services: Services
) -> None:
    await seed(db, "AAPL", FOLDABLE, DAY, score=0.8)
    await seed(db, "AAPL", FOLDABLE_ALT, DAY - timedelta(hours=1), score=0.4)
    await db[ARTICLES].update_one(
        {"dedupe_key": dedupe_key(FOLDABLE, "Wire")},
        {
            "$set": {
                "similar": [
                    {
                        "title": "Another outlet",
                        "url": "https://news.example.com/z",
                        "source": "Wire Z",
                        "published_at": DAY,
                    }
                ]
            }
        },
    )

    page = await services.news_feed.page("AAPL")

    group = page.articles[0]
    assert group.sentiment == pytest.approx(0.6)  # recorded look-alikes have no score
    assert len(group.similar) == 2


async def test_scored_articles_for_the_study_never_include_low_value_documents(
    db: Database, services: Services
) -> None:
    await seed(db, "AAPL", "Apple unveils new MacBook lineup", CLOSED_NOW - timedelta(days=3), 0.5)
    await seed(
        db,
        "AAPL",
        "Apple Inc. $AAPL Holdings Trimmed by Birch Capital",
        CLOSED_NOW - timedelta(days=3),
        0.5,
    )
    await NewsMaintenanceRepository(db).backfill_flags()

    articles, _ = await services.news.scored_articles(
        "AAPL", CLOSED_NOW - timedelta(days=30), CLOSED_NOW
    )

    assert [a.title for a in articles] == ["Apple unveils new MacBook lineup"]


async def test_ingest_inserted_documents_never_carry_is_low_value_true(
    db: Database, clock: FakeClock
) -> None:
    items = [
        _news("Apple Inc. $AAPL Stake Cut by Denali Advisors LLC", DAY),
        _news("Apple unveils new MacBook lineup", DAY, "Wire B"),
        _news("Apple stock drops 6% after report", DAY, "Wire C"),
    ]

    await _run(db, clock, items)

    flags = [d["is_low_value"] async for d in db[ARTICLES].find({})]
    assert flags == [False, False]  # the filing was dropped, never stored with the flag


async def test_ingest_item_folded_for_one_symbol_is_still_stored_for_another(
    db: Database, clock: FakeClock
) -> None:
    first = "Apple and Microsoft sign a big cloud deal for Siri"
    second = "Apple and Microsoft: big Siri cloud deal signed"
    await _run(
        db, clock, [_news(first, DAY, "Wire A"), _news(second, DAY + timedelta(hours=1), "Wire B")]
    )
    assert await db[ARTICLES].count_documents({"title": second}) == 0  # folded for AAPL
    clock.now += timedelta(hours=7)

    # MSFT has nothing kept that day, so for MSFT the same item is a story of its own.
    await _run(db, clock, [_news(second, DAY + timedelta(hours=1), "Wire B")], symbol="MSFT")

    stored = await db[ARTICLES].find_one({"title": second})
    assert stored is not None
    assert stored["symbols"] == ["MSFT"]


async def test_ingest_item_already_stored_on_another_day_is_not_a_duplicate_candidate(
    db: Database, clock: FakeClock
) -> None:
    await _run(db, clock, [_news(FOLDABLE, DAY, "Wire A")])
    clock.now += timedelta(hours=7)

    # The same article, now reported a day later: already stored, so nothing is folded.
    await _run(db, clock, [_news(FOLDABLE, DAY + timedelta(days=1), "Wire A")])

    docs = await _docs(db)
    assert len(docs) == 1
    assert "similar_count" not in docs[f"{FOLDABLE}|Wire A"]


async def test_ingest_stored_recap_is_never_a_fold_target(db: Database, clock: FakeClock) -> None:
    recap = "Apple shares jump 5% on iPhone launch news today"
    assert is_price_recap(recap)
    await seed(db, "AAPL", recap, DAY)  # stored but not flagged yet (backfill has not run)

    await _run(db, clock, [_news("Apple shares jump on iPhone launch news today", DAY, "Wire B")])

    docs = await _docs(db)
    assert len(docs) == 2
    assert all("similar_count" not in d for d in docs.values())


async def test_add_similar_is_atomic_and_idempotent_under_concurrent_writers(
    db: Database,
) -> None:
    await seed(db, "AAPL", FOLDABLE, DAY)
    main = dedupe_key(FOLDABLE, "Wire")
    maint = NewsMaintenanceRepository(db)
    entries: list[SimilarEntry] = [
        similar_entry(_news(FOLDABLE_ALT, DAY + timedelta(minutes=n), f"Wire {n}"))
        for n in range(1, 9)
    ]

    results = await asyncio.gather(*(maint.add_similar({main: [e]}) for e in entries))
    again = await maint.add_similar({main: entries})

    doc = await db[ARTICLES].find_one({"dedupe_key": main})
    assert doc is not None
    assert sum(results) == 8
    assert again == 0
    assert doc["similar_count"] == 8
    assert len(doc["similar_keys"]) == 8
    assert [e["source"] for e in doc["similar"]][:2] == ["Wire 8", "Wire 7"]


async def test_backfill_folds_stored_near_duplicates_and_is_idempotent(db: Database) -> None:
    for n in range(12):  # ordinary Apple headlines, one a day, so "apple" is the shared word
        await seed(
            db, "AAPL", f"Apple filler headline number{n} {'x' * n}", DAY - timedelta(days=n + 3)
        )
    await seed(db, "AAPL", FOLDABLE, DAY)  # earliest of the day: stays
    await seed(db, "AAPL", FOLDABLE_ALT, DAY + timedelta(hours=1))
    await seed(db, "AAPL", "Apple delays foldable iPhone debut to 2027", DAY + timedelta(hours=2))
    await seed(db, "AAPL", "Apple unveils new MacBook lineup", DAY)  # unrelated: stays
    await seed(db, "AAPL", FOLDABLE, DAY + timedelta(days=2))  # another day: stays
    # A duplicate that another symbol also holds only loses AAPL.
    shared = "Apple delays foldable iPhone launch until 2027"
    await seed(db, "AAPL", shared, DAY + timedelta(hours=3), symbols=["AAPL", "MSFT"])

    first = await backfill_stored_news(db)
    second = await backfill_stored_news(db)

    assert (first.folded, second.folded) == (3, 0)
    main = await db[ARTICLES].find_one({"title": FOLDABLE, "published_at": DAY})
    assert main is not None
    assert main["similar_count"] == 3
    assert {e["title"] for e in main["similar"]} == {
        FOLDABLE_ALT,
        "Apple delays foldable iPhone debut to 2027",
        shared,
    }
    assert await db[ARTICLES].count_documents({"title": FOLDABLE_ALT}) == 0  # nobody else held it
    kept_shared = await db[ARTICLES].find_one({"title": shared})
    assert kept_shared is not None
    assert kept_shared["symbols"] == ["MSFT"]  # AAPL was unlinked, MSFT keeps the story
    state = await db[STATE].find_one({"symbol": "AAPL"})
    assert state is not None
    assert state["dedupe_version"] == 1


async def test_backfill_leaves_recaps_and_other_days_alone(db: Database) -> None:
    recap = "Apple shares jump 5% on iPhone launch news today"
    await seed(db, "AAPL", recap, DAY)
    await seed(
        db, "AAPL", "Apple shares jump on iPhone launch news today", DAY + timedelta(hours=1)
    )
    await seed(db, "AAPL", FOLDABLE, DAY)
    await seed(db, "AAPL", FOLDABLE_ALT, DAY + timedelta(days=1))

    summary = await backfill_stored_news(db)

    assert summary.folded == 0
    assert await db[ARTICLES].count_documents({}) == 4


async def test_backfill_fold_failure_for_one_symbol_is_logged_not_raised(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    await seed(db, "AAPL", FOLDABLE, DAY)

    async def boom(_self: NewsMaintenanceRepository, _symbol: str) -> list[object]:
        raise RuntimeError("mongo hiccup")

    monkeypatch.setattr(NewsMaintenanceRepository, "showable_articles", boom)

    summary = await backfill_stored_news(db)

    assert summary.folded == 0
    assert await db[STATE].count_documents({"dedupe_version": {"$exists": True}}) == 0  # retried


async def test_service_backfill_runs_in_the_background_and_shutdown_cancels_it(
    db: Database, services: Services
) -> None:
    await seed(db, "AAPL", "Apple stock drops 6% after report", DAY)

    services.news.backfill_flags()
    services.news.backfill_flags()  # idempotent while one is running or done
    await services.aclose()

    # Either it finished before the cancel or it was cancelled cleanly; it never raises.
    doc = await db[ARTICLES].find_one({})
    assert doc is not None


async def test_feed_hides_a_stored_similar_entry_that_is_its_own_row_on_the_page(
    db: Database, services: Services
) -> None:
    other = "Apple opens a flagship store in Mumbai"
    await seed(db, "AAPL", FOLDABLE, DAY)
    await seed(db, "AAPL", other, DAY - timedelta(days=3))  # shared with another symbol
    entry = {
        "title": other,
        "url": "https://news.example.com/o",
        "source": "Wire",
        "published_at": DAY - timedelta(days=3),
    }
    await db[ARTICLES].update_one(
        {"dedupe_key": dedupe_key(FOLDABLE, "Wire")}, {"$set": {"similar": [entry]}}
    )

    page = await services.news_feed.page("AAPL")

    by_title = {a.title: a for a in page.articles}
    assert set(by_title) == {FOLDABLE, other}
    assert by_title[FOLDABLE].similar == []  # the story is already its own row


async def test_backfill_skips_and_does_not_mark_a_symbol_being_ingested(db: Database) -> None:
    await seed(db, "AAPL", FOLDABLE, DAY)
    await seed(db, "AAPL", FOLDABLE_ALT, DAY + timedelta(hours=1))

    summary = await backfill_stored_news(db, is_running=lambda symbol: symbol == "AAPL")

    assert summary.folded == 0
    assert await db[ARTICLES].count_documents({}) == 2
    assert await db[STATE].count_documents({"dedupe_version": {"$exists": True}}) == 0


async def test_backfill_uses_the_real_company_name_when_one_is_known(db: Database) -> None:
    # The pair shares stock, market and outlook (3 tokens) once the company name is ignored.
    await seed(db, "AAPL", "Apple stock market outlook brightens", DAY)
    await seed(db, "AAPL", "Apple stock market outlook improves", DAY + timedelta(hours=1))
    names: list[str] = []

    async def name(symbol: str) -> str:
        names.append(symbol)
        return "Apple Inc."

    summary = await backfill_stored_news(db, company_name=name)

    assert names == ["AAPL"]
    assert summary.folded == 1  # real name ignored; stock, market, outlook still match
