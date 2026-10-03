from datetime import timedelta

import pytest

from app.db import Database
from app.providers.errors import RateLimitedError
from app.providers.models import NewsItem
from app.repositories.news import ARTICLES, STATE, NewsRepository
from app.services.container import Services
from tests.services.fakes import CLOSED_NOW, FakeClock, FakeNews, FakeScorer, Sleeps

pytestmark = pytest.mark.integration

START = CLOSED_NOW - timedelta(days=730)


async def _ingest(services: Services, symbol: str = "AAPL", name: str = "Apple Inc.") -> None:
    await services.news.ensure_ingested(symbol, name)
    await services.news.wait(symbol)


async def test_ensure_ingested_first_call_reports_progress_and_runs_in_background(
    services: Services,
) -> None:
    progress = await services.news.ensure_ingested("AAPL", "Apple Inc.")

    assert progress.in_progress
    assert progress.months_total == 24
    await services.news.wait("AAPL")
    assert (await services.news.progress("AAPL")).months_done == 24


async def test_ensure_ingested_concurrent_calls_start_one_task(
    services: Services, news_provider: FakeNews
) -> None:
    await services.news.ensure_ingested("AAPL", "Apple Inc.")
    await services.news.ensure_ingested("AAPL", "Apple Inc.")
    await services.news.wait("AAPL")

    month_queries = [q for q in news_provider.queries if q.start.day == 1]
    assert len(month_queries) == 24  # each month fetched exactly once


async def test_ensure_ingested_second_run_is_idempotent_and_fetches_nothing(
    services: Services, news_provider: FakeNews, db: Database
) -> None:
    await _ingest(services)
    fetched = len(news_provider.queries)
    stored = await db[ARTICLES].count_documents({})

    progress = await services.news.ensure_ingested("AAPL", "Apple Inc.")
    await services.news.wait("AAPL")

    assert not progress.in_progress
    assert len(news_provider.queries) == fetched
    assert await db[ARTICLES].count_documents({}) == stored


async def test_ingestion_dedupes_republished_stories(services: Services, db: Database) -> None:
    await _ingest(services)

    titles = [doc["title"].lower().rstrip("!") async for doc in db[ARTICLES].find({})]
    assert len(titles) == len(set(titles))


async def test_ingestion_filters_irrelevant_articles(services: Services, db: Database) -> None:
    await _ingest(services)

    assert (
        await db[ARTICLES].count_documents({"title": {"$regex": "orchard", "$options": "i"}}) == 0
    )
    assert await db[ARTICLES].count_documents({}) > 0


async def test_same_story_for_two_symbols_gains_both_in_symbols_array(
    services: Services, db: Database
) -> None:
    item = NewsItem.model_validate(
        {
            "url": "https://x.example.com/a",
            "title": "Apple and Microsoft sign a deal",
            "summary": None,
            "source": "Example Wire",
            "published_at": CLOSED_NOW,
            "provider": "t",
        }
    )
    repo = NewsRepository(db)

    await repo.upsert_articles("AAPL", [item])
    await repo.upsert_articles("MSFT", [item])

    docs = [d async for d in db[ARTICLES].find({})]
    assert len(docs) == 1
    assert sorted(docs[0]["symbols"]) == ["AAPL", "MSFT"]


async def test_ingestion_scores_articles_in_batches_of_64(
    services: Services, scorer: FakeScorer
) -> None:
    await _ingest(services)

    assert scorer.batches
    assert max(scorer.batches) <= 64
    assert sum(scorer.batches) > 64  # more than one batch's worth overall


async def test_scored_articles_after_ingestion_are_ok_and_in_range(services: Services) -> None:
    await _ingest(services)

    articles, status = await services.news.scored_articles("AAPL", START, CLOSED_NOW)

    assert status.state == "ok"
    assert len(articles) > 100
    assert all(START <= a.published_at <= CLOSED_NOW for a in articles)
    assert all(-1.0 <= a.score <= 1.0 for a in articles)


async def test_scored_articles_while_ingestion_incomplete_is_partial_with_progress(
    services: Services, news_provider: FakeNews
) -> None:
    news_provider.fail_windows = {"2025-03", "2025-04"}
    await _ingest(services)

    _, status = await services.news.scored_articles("AAPL", START, CLOSED_NOW)

    assert status.state == "partial"
    assert status.reason is not None
    assert "22 of 24 months" in status.reason


async def test_failed_window_is_skipped_logged_and_retried_on_next_run(
    services: Services, news_provider: FakeNews, clock: FakeClock
) -> None:
    news_provider.fail_windows = {"2025-03"}
    await _ingest(services)
    assert (await services.news.progress("AAPL")).months_done == 23

    news_provider.fail_windows = set()
    clock.now = CLOSED_NOW + timedelta(minutes=10)  # past the 5 minute retry pause
    await _ingest(services)

    assert (await services.news.progress("AAPL")).months_done == 24


async def test_failed_run_is_not_retried_immediately(
    services: Services, news_provider: FakeNews
) -> None:
    news_provider.fail_windows = {"2025-03"}
    await _ingest(services)
    calls = len(news_provider.queries)

    progress = await services.news.ensure_ingested("AAPL", "Apple Inc.")

    assert not progress.in_progress
    assert len(news_provider.queries) == calls


async def test_sentiment_unavailable_leaves_articles_unscored_and_flags_status(
    services: Services, scorer: FakeScorer, db: Database
) -> None:
    scorer.available = False

    await _ingest(services)

    articles, status = await services.news.scored_articles("AAPL", START, CLOSED_NOW)
    assert articles == []
    assert status.state == "unavailable"
    assert status.reason is not None
    assert "sentiment model is not installed" in status.reason
    assert await db[ARTICLES].count_documents({"sentiment": None}) > 0


async def test_sentiment_recovers_on_next_ingestion(
    services: Services, scorer: FakeScorer, clock: FakeClock
) -> None:
    scorer.available = False
    await _ingest(services)
    scorer.available = True
    clock.now = CLOSED_NOW + timedelta(hours=7)  # incremental pass is due again

    await _ingest(services)

    articles, status = await services.news.scored_articles("AAPL", START, clock.now)
    assert articles
    assert status.state == "ok"


async def test_provider_failure_everywhere_never_raises_and_records_error(
    services: Services, news_provider: FakeNews, db: Database
) -> None:
    news_provider.fail_with = RateLimitedError("google_news")

    await _ingest(services)

    state = await db[STATE].find_one({"symbol": "AAPL"})
    assert state is not None
    assert state["in_progress_since"] is None
    assert "rate limited" in state["last_error"]


async def test_minute_quota_pauses_then_retries_same_window(
    services: Services, news_provider: FakeNews, sleeps: Sleeps
) -> None:
    news_provider.quota_hits = 2

    await _ingest(services)

    assert sleeps.waited == [20.0, 20.0]  # until retry_at, well under the 65s cap
    assert (await services.news.progress("AAPL")).months_done == 24  # nothing was skipped


async def test_minute_quota_wait_is_capped_at_65_seconds(
    services: Services, news_provider: FakeNews, sleeps: Sleeps, clock: FakeClock
) -> None:
    news_provider.quota_hits = 1
    clock.now = CLOSED_NOW - timedelta(minutes=10)  # retry_at is now 10 minutes + 20s away

    await _ingest(services)

    assert sleeps.waited == [65.0]


async def test_day_quota_stops_run_immediately_and_records_error(
    services: Services, news_provider: FakeNews, sleeps: Sleeps, db: Database
) -> None:
    news_provider.quota_hits = 1000
    news_provider.quota_window = "day"

    await _ingest(services)

    assert sleeps.waited == []
    assert len(news_provider.queries) == 1  # no hammering of the remaining 23 windows
    state = await db[STATE].find_one({"symbol": "AAPL"})
    assert state is not None
    assert "day quota exhausted" in state["last_error"]
    assert state["in_progress_since"] is None
