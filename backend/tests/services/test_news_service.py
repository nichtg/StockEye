from datetime import timedelta

import pytest

from app.config import ProviderLimits
from app.db import Database
from app.providers.errors import RateLimitedError
from app.providers.models import NewsItem
from app.providers.resilience import ProviderGuard
from app.repositories.news import ARTICLES, STATE, NewsRepository
from app.repositories.quotas import QuotaLedger
from app.repositories.quotas import install_indexes as quota_indexes
from app.services.container import Services
from app.services.news import INGEST_FAILED, NewsService
from tests.services.fakes import CLOSED_NOW, NAMES, FakeClock, FakeNews, FakeScorer

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
    assert state["last_error"] == INGEST_FAILED  # vendor details stay in the logs


async def test_minute_quota_skips_the_window_and_it_is_retried_on_next_run(
    services: Services, news_provider: FakeNews, clock: FakeClock
) -> None:
    news_provider.quota_hits = 1  # the first backfill month hits the per-minute throttle

    await _ingest(services)
    assert (await services.news.progress("AAPL")).months_done == 23

    clock.now = CLOSED_NOW + timedelta(minutes=10)  # past the 5 minute retry pause
    await _ingest(services)

    assert (await services.news.progress("AAPL")).months_done == 24


async def test_day_quota_stops_run_immediately_and_records_error(
    services: Services, news_provider: FakeNews, db: Database
) -> None:
    news_provider.quota_hits = 1000
    news_provider.quota_window = "day"

    await _ingest(services)

    assert len(news_provider.queries) == 1  # no hammering of the remaining 23 windows
    state = await db[STATE].find_one({"symbol": "AAPL"})
    assert state is not None
    assert state["last_error"] == INGEST_FAILED
    assert state["in_progress_since"] is None


async def test_incremental_skips_providers_that_do_not_cover_the_exchange_and_spends_no_quota(
    db: Database, clock: FakeClock, scorer: FakeScorer
) -> None:
    ledger = QuotaLedger(db)
    await quota_indexes(db)
    limits = {"google_news": ProviderLimits(per_minute=100, per_day=1000)} | {
        "alphavantage": ProviderLimits(per_minute=5, per_day=25)
    }
    guard = ProviderGuard(ledger, limits, 0.8, clock=clock)
    us_only = FakeNews("alphavantage", exchanges=frozenset({"US"}))
    google = FakeNews()
    news = NewsService(
        db,
        guard.wrap_news(google),
        [guard.wrap_news(us_only), guard.wrap_news(google)],
        scorer,
        clock=clock,
    )

    await news.ensure_ingested("D05.SI", "DBS Group Holdings Ltd")
    await news.wait("D05.SI")

    assert us_only.queries == []
    assert (
        await ledger.snapshot("alphavantage", limits["alphavantage"], CLOSED_NOW)
    ).used_today == 0
    assert google.queries  # the covering provider still ran


async def test_incremental_still_uses_a_provider_that_covers_the_exchange(
    db: Database, clock: FakeClock, scorer: FakeScorer
) -> None:
    us_only = FakeNews("finnhub", exchanges=frozenset({"US"}))
    google = FakeNews()
    news = NewsService(db, google, [us_only, google], scorer, clock=clock)

    await news.ensure_ingested("AAPL", "Apple Inc.")
    await news.wait("AAPL")

    assert len(us_only.queries) == 1


async def test_ingestions_run_at_most_max_concurrent_at_a_time(
    db: Database, clock: FakeClock, scorer: FakeScorer
) -> None:
    google = FakeNews()
    news = NewsService(db, google, [google], scorer, max_concurrent=1, clock=clock)

    for symbol in ("AAPL", "MSFT", "SPY"):
        await news.ensure_ingested(symbol, NAMES[symbol])
    await news.wait()

    assert google.max_active == 1
    for symbol in ("AAPL", "MSFT", "SPY"):
        assert (await news.progress(symbol)).months_done == 24  # queued, not dropped


async def test_finished_ingestions_are_forgotten(services: Services) -> None:
    await _ingest(services)

    assert not services.news._tasks  # a long-lived service must not keep every task it ever ran
    assert not (await services.news.progress("AAPL")).in_progress


async def test_has_history_is_false_until_ingestion_starts_then_true(services: Services) -> None:
    assert not await services.news.has_history("AAPL")

    await _ingest(services)

    assert await services.news.has_history("AAPL")
