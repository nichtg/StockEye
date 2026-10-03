"""News use-cases: background ingestion, relevance filtering, sentiment scoring, and reads.

Ingestion runs as an ``asyncio.Task`` per symbol (never two at once, and at most a few overall)
and never raises: failures are logged, the ingest state records only that one happened, and the
failed window is simply retried on the next run. Backfill windows are whole calendar months (so
their ``YYYY-MM`` keys stay stable from day to day) fetched from one ``backfill`` provider; the
current, partial month is covered by the incremental pass over every ``live`` provider that covers
the symbol's exchange. Providers arrive already guarded.
"""

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from app.clock import utc_now
from app.db import Database
from app.domain.macro import ScoredArticle
from app.logging_setup import get_logger
from app.providers.base import NewsProvider
from app.providers.errors import ProviderError, QuotaExhaustedError
from app.providers.google_news import monthly_windows
from app.providers.models import NewsItem, NewsQuery
from app.repositories.news import ArticleText, IngestState, NewsRepository, SentimentRecord
from app.sentiment.scorer import SentimentScore, SentimentScorer, SentimentUnavailableError
from app.services.calendars import exchange_for, root_ticker
from app.services.status import DataStatus, ok

log = get_logger(__name__)

BACKFILL_MONTHS = 24
INCREMENTAL_DAYS = 30
INCREMENTAL_EVERY = timedelta(hours=6)
RETRY_AFTER_ATTEMPT = timedelta(minutes=5)  # do not hammer providers after a failed run
STALE_RUN_AFTER = timedelta(minutes=30)  # an "in progress" marker older than this is a crash
SCORE_BATCH = 64
# Vendor error text can echo request details, so state (shown to users) gets this instead.
INGEST_FAILED = "News collection failed; it will retry automatically."

_SUFFIXES = frozenset(
    {"inc", "corp", "corporation", "ltd", "limited", "holdings", "group", "co", "plc", "nv", "sa"}
)
_NAME_NOISE = re.compile(r"[^\w&\s-]")
_SPACES = re.compile(r"\s+")
_MIN_TICKER_LENGTH = 3

SENTIMENT_DOWN_REASON = (
    "News sentiment is unavailable: the sentiment model is not installed or could not be loaded."
)


def core_name(company_name: str) -> str:
    """Company name without legal suffixes and punctuation, e.g. "DBS Group Holdings Ltd" -> "DBS".

    Only trailing suffix words are stripped, so a name that is nothing but suffixes is kept whole.
    """
    cleaned = _SPACES.sub(" ", _NAME_NOISE.sub("", company_name.replace(".", ""))).strip()
    words = cleaned.split(" ")
    while len(words) > 1 and words[-1].lower() in _SUFFIXES:
        words.pop()
    return " ".join(words)


def is_relevant(symbol: str, company_name: str, title: str, summary: str | None) -> bool:
    """Keep articles that mention the company's core name or the ticker as a whole word.

    Google News matches loosely, so without this filter a query for "Apple" returns orchard news.
    """
    text = f"{title} {summary or ''}"
    name = core_name(company_name)
    if name and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.IGNORECASE):
        return True
    root = root_ticker(symbol)
    return len(root) >= _MIN_TICKER_LENGTH and bool(
        re.search(rf"(?<![\w.]){re.escape(root)}(?![\w])", text)
    )


@dataclass(frozen=True)
class IngestProgress:
    months_done: int
    months_total: int
    in_progress: bool


def _month_start(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _missing(
    windows: list[tuple[datetime, datetime]], state: IngestState
) -> list[tuple[datetime, datetime]]:
    return [w for w in windows if w[0].strftime("%Y-%m") not in state.backfilled_months]


def _progress(
    windows: list[tuple[datetime, datetime]], state: IngestState, in_progress: bool
) -> IngestProgress:
    return IngestProgress(len(windows) - len(_missing(windows, state)), len(windows), in_progress)


class NewsService:
    def __init__(
        self,
        db: Database,
        backfill: NewsProvider,
        live: list[NewsProvider],
        scorer: SentimentScorer,
        *,
        max_concurrent: int = 2,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repo = NewsRepository(db)
        self._backfill = backfill  # the one adapter that can reach far back
        self._live = live
        self._scorer = scorer
        self._clock = clock
        self._tasks: dict[str, asyncio.Task[None]] = {}  # running ingestions only
        self._gate = asyncio.Semaphore(max_concurrent)  # vendors and the scorer are shared

    # --- ingestion -------------------------------------------------------------------------

    def _windows(self, now: datetime) -> list[tuple[datetime, datetime]]:
        return monthly_windows(_month_start(now), BACKFILL_MONTHS)

    async def has_history(self, symbol: str) -> bool:
        """Whether ingestion has ever started for ``symbol`` (so it is not a new symbol)."""
        state = await self._repo.get_state(symbol)
        return state.last_attempt_at is not None or bool(state.backfilled_months)

    async def ensure_ingested(self, symbol: str, company_name: str) -> IngestProgress:
        """Start background ingestion if months are missing or the data is over 6 hours old.

        Idempotent: while a task for ``symbol`` runs, further calls only report progress.
        """
        now = self._clock()
        windows = self._windows(now)
        state = await self._repo.get_state(symbol)
        progress = _progress(windows, state, self._running(symbol))
        if progress.in_progress:
            return progress
        complete = progress.months_done == progress.months_total
        due = not complete or (
            state.last_incremental_at is None or now - state.last_incremental_at > INCREMENTAL_EVERY
        )
        recently_tried = (
            state.last_attempt_at is not None and now - state.last_attempt_at < RETRY_AFTER_ATTEMPT
        )
        foreign_run = (
            state.in_progress_since is not None and now - state.in_progress_since < STALE_RUN_AFTER
        )
        if not due or recently_tried or foreign_run:
            return replace(progress, in_progress=foreign_run)
        # No await between the running check above and this insert, so two callers cannot both
        # start a task for one symbol.
        task = asyncio.create_task(self._run(symbol, company_name, windows))
        self._tasks[symbol] = task
        task.add_done_callback(lambda done: self._forget(symbol, done))
        return replace(progress, in_progress=True)

    def _forget(self, symbol: str, task: asyncio.Task[None]) -> None:
        if self._tasks.get(symbol) is task:
            del self._tasks[symbol]

    def _running(self, symbol: str) -> bool:
        task = self._tasks.get(symbol)
        return task is not None and not task.done()

    async def wait(self, symbol: str | None = None) -> None:
        """Wait for running ingestion (one symbol, or all). For jobs and tests."""
        if symbol is None:
            tasks = list(self._tasks.values())
        else:
            tasks = [self._tasks[symbol]] if symbol in self._tasks else []
        await asyncio.gather(*tasks, return_exceptions=True)

    async def shutdown(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    async def _run(
        self, symbol: str, company_name: str, windows: list[tuple[datetime, datetime]]
    ) -> None:
        """The task body. Catches everything: a background task must never take the app down."""
        failed = False
        try:
            async with self._gate:
                await self._repo.begin_run(symbol, self._clock())
                failed = await self._ingest(symbol, company_name, windows)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("news_ingest_crashed", symbol=symbol)
            failed = True
        error = INGEST_FAILED if failed else None
        try:
            await self._repo.end_run(symbol, error)
        except Exception:
            log.exception("news_ingest_state_write_failed", symbol=symbol)

    async def _ingest(
        self, symbol: str, company_name: str, windows: list[tuple[datetime, datetime]]
    ) -> bool:
        """Backfill then incremental pass; True if any window failed (details are logged)."""
        state = await self._repo.get_state(symbol)
        missing = _missing(windows, state)
        try:
            failures = await self._backfill_months(symbol, company_name, missing)
        except QuotaExhaustedError as exc:
            # The daily budget is gone: every remaining window would fail the same way.
            log.warning("news_backfill_stopped", symbol=symbol, error=str(exc))
            return True
        now = self._clock()
        recent = self._query(symbol, company_name, now - timedelta(days=INCREMENTAL_DAYS), now)
        incremental_failures = await self._incremental(symbol, company_name, recent)
        if not incremental_failures:
            await self._repo.mark_incremental(symbol, now)
        return bool(failures or incremental_failures)

    def _query(self, symbol: str, company_name: str, start: datetime, end: datetime) -> NewsQuery:
        return NewsQuery(
            symbol=symbol,
            exchange=exchange_for(symbol),
            company_name=company_name,
            start=start,
            end=end,
        )

    async def _backfill_months(
        self, symbol: str, company_name: str, windows: list[tuple[datetime, datetime]]
    ) -> int:
        """Fetch and store each missing month; returns how many months were skipped.

        A skipped month is retried on the next run. Only a daily quota error propagates, since
        it dooms every remaining window.
        """
        failures = 0
        for start, end in windows:
            month = start.strftime("%Y-%m")
            try:
                items = await self._backfill.fetch(self._query(symbol, company_name, start, end))
            except ProviderError as exc:
                if isinstance(exc, QuotaExhaustedError) and exc.window == "day":
                    raise
                failures += 1
                log.warning(
                    "news_window_failed",
                    symbol=symbol,
                    provider=self._backfill.name,
                    window=month,
                    error=str(exc),
                )
                continue
            await self._store(symbol, company_name, items)
            await self._repo.mark_month_done(symbol, month)
        return failures

    async def _incremental(self, symbol: str, company_name: str, recent: NewsQuery) -> int:
        """Fetch the last ``INCREMENTAL_DAYS`` from every covering live provider; count failures.

        A provider that does not cover the query's exchange is skipped before it is called, so
        it costs no quota.
        """
        providers = [p for p in self._live if recent.exchange in p.exchanges]
        results = await asyncio.gather(
            *(provider.fetch(recent) for provider in providers), return_exceptions=True
        )
        failures = 0
        for provider, result in zip(providers, results, strict=True):
            if isinstance(result, ProviderError):
                failures += 1
                log.warning(
                    "news_window_failed", symbol=symbol, provider=provider.name, error=str(result)
                )
            elif isinstance(result, BaseException):
                raise result
            else:
                await self._store(symbol, company_name, result)
        return failures

    async def _store(self, symbol: str, company_name: str, items: list[NewsItem]) -> None:
        relevant = [i for i in items if is_relevant(symbol, company_name, i.title, i.summary)]
        await self._repo.upsert_articles(symbol, relevant)
        await self._score(symbol)

    async def _score(self, symbol: str) -> None:
        """Score every unscored article for ``symbol`` in batches; stop quietly if no model."""
        while batch := await self._repo.unscored(symbol, SCORE_BATCH):
            try:
                scores = await asyncio.to_thread(self._scorer.score, [a.text for a in batch])
                version = self._scorer.model_version
            except SentimentUnavailableError as exc:
                log.warning("sentiment_unavailable", symbol=symbol, error=str(exc))
                await self._repo.set_scoring_error(symbol, str(exc))
                return
            await self._repo.save_scores(_records(batch, scores, version))
        await self._repo.set_scoring_error(symbol, None)

    # --- reads -----------------------------------------------------------------------------

    async def progress(self, symbol: str) -> IngestProgress:
        state = await self._repo.get_state(symbol)
        return self._progress_of(symbol, state)

    def _progress_of(self, symbol: str, state: IngestState) -> IngestProgress:
        return _progress(self._windows(self._clock()), state, self._running(symbol))

    async def status(self, symbol: str) -> DataStatus:
        """News status from ingest state alone (no fetching, no scoring)."""
        state = await self._repo.get_state(symbol)
        return self._status_of(symbol, state)

    def _status_of(self, symbol: str, state: IngestState) -> DataStatus:
        progress = self._progress_of(symbol, state)
        if state.scoring_error is not None:
            return DataStatus(state="unavailable", as_of=None, reason=SENTIMENT_DOWN_REASON)
        if progress.months_done < progress.months_total:
            if progress.in_progress or state.last_attempt_at is None:
                reason = (
                    f"News is still being collected ({progress.months_done} of "
                    f"{progress.months_total} months so far)."
                )
            else:
                reason = (
                    f"News is incomplete ({progress.months_done} of {progress.months_total} "
                    "months collected): a source did not respond. "
                    "The rest will be retried automatically."
                )
            return DataStatus(state="partial", as_of=state.last_incremental_at, reason=reason)
        return ok(state.last_incremental_at)

    async def scored_articles(
        self, symbol: str, start: datetime, end: datetime
    ) -> tuple[list[ScoredArticle], DataStatus]:
        articles = await self._repo.scored(symbol, start, end)
        state = await self._repo.get_state(symbol)
        status = self._status_of(symbol, state)
        if status.state == "ok" and not articles:
            status = ok(status.as_of, "No news articles about this company were found.")
        return articles, status


def _records(
    batch: list[ArticleText], scores: list[SentimentScore], version: str
) -> list[SentimentRecord]:
    return [
        SentimentRecord(a.id, s.positive, s.negative, s.neutral, s.score, version)
        for a, s in zip(batch, scores, strict=True)
    ]
