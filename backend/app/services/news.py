"""News use-cases: background ingestion, relevance filtering, sentiment scoring, and reads.

Ingestion runs as an ``asyncio.Task`` per symbol (never two at once) and never raises: failures
are logged and recorded in the ingest state, and the failed window is simply retried on the next
run. Backfill windows are whole calendar months (so their ``YYYY-MM`` keys stay stable from day
to day); the current, partial month is covered by the incremental pass.
"""

import asyncio
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Protocol

from app.db import Database
from app.domain.macro import ScoredArticle
from app.logging_setup import get_logger
from app.providers.base import NewsProvider
from app.providers.errors import ProviderError, QuotaExhaustedError
from app.providers.google_news import monthly_windows
from app.providers.models import NewsItem, NewsQuery
from app.providers.resilience import ProviderGuard
from app.repositories.news import ArticleText, IngestState, NewsRepository, SentimentRecord
from app.sentiment.scorer import SentimentScore, SentimentUnavailableError
from app.services.status import DataStatus, ok

log = get_logger(__name__)

BACKFILL_MONTHS = 24
INCREMENTAL_DAYS = 30
INCREMENTAL_EVERY = timedelta(hours=6)
RETRY_AFTER_ATTEMPT = timedelta(minutes=5)  # do not hammer providers after a failed run
STALE_RUN_AFTER = timedelta(minutes=30)  # an "in progress" marker older than this is a crash
MAX_QUOTA_WAIT = 65.0  # seconds; one minute window plus a margin
MAX_QUOTA_WAITS = 5
SCORE_BATCH = 64
BACKFILL_PROVIDER = "google_news"  # the only adapter that can reach far back

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
    root = symbol.upper().removesuffix(".SI")
    return len(root) >= _MIN_TICKER_LENGTH and bool(
        re.search(rf"(?<![\w.]){re.escape(root)}(?![\w])", text)
    )


@dataclass(frozen=True)
class IngestProgress:
    months_done: int
    months_total: int
    in_progress: bool


class ScorerPort(Protocol):
    """What the service needs from a scorer (``model_version`` read-only, as on FinBERT)."""

    @property
    def model_version(self) -> str: ...

    def score(self, texts: Sequence[str]) -> list[SentimentScore]: ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _month_start(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class NewsService:
    def __init__(
        self,
        db: Database,
        providers: list[NewsProvider],
        guard: ProviderGuard,
        scorer: ScorerPort,
        *,
        clock: Callable[[], datetime] = _utc_now,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._sleep = sleep
        self._repo = NewsRepository(db)
        self._providers = providers
        self._guard = guard
        self._scorer = scorer
        self._clock = clock
        self._tasks: dict[str, asyncio.Task[None]] = {}

    # --- ingestion -------------------------------------------------------------------------

    def _windows(self, now: datetime) -> list[tuple[datetime, datetime]]:
        return monthly_windows(_month_start(now), BACKFILL_MONTHS)

    async def ensure_ingested(self, symbol: str, company_name: str) -> IngestProgress:
        """Start background ingestion if months are missing or the data is over 6 hours old.

        Idempotent: while a task for ``symbol`` runs, further calls only report progress.
        """
        now = self._clock()
        windows = self._windows(now)
        state = await self._repo.get_state(symbol)
        missing = [w for w in windows if w[0].strftime("%Y-%m") not in state.backfilled_months]
        total = len(windows)
        if self._running(symbol):
            return IngestProgress(total - len(missing), total, True)
        due = bool(missing) or (
            state.last_incremental_at is None or now - state.last_incremental_at > INCREMENTAL_EVERY
        )
        recently_tried = (
            state.last_attempt_at is not None and now - state.last_attempt_at < RETRY_AFTER_ATTEMPT
        )
        foreign_run = (
            state.in_progress_since is not None and now - state.in_progress_since < STALE_RUN_AFTER
        )
        # No awaits between the registry re-check and the insert, so two callers cannot both start.
        if due and not recently_tried and not foreign_run and not self._running(symbol):
            self._tasks[symbol] = asyncio.create_task(self._run(symbol, company_name, windows))
            return IngestProgress(total - len(missing), total, True)
        return IngestProgress(total - len(missing), total, foreign_run)

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
        error: str | None = None
        try:
            await self._repo.begin_run(symbol, self._clock())
            error = await self._ingest(symbol, company_name, windows)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("news_ingest_crashed", symbol=symbol)
            error = f"{type(exc).__name__}: {exc}"
        try:
            await self._repo.end_run(symbol, error)
        except Exception:
            log.exception("news_ingest_state_write_failed", symbol=symbol)

    async def _ingest(
        self, symbol: str, company_name: str, windows: list[tuple[datetime, datetime]]
    ) -> str | None:
        state = await self._repo.get_state(symbol)
        failures: list[str] = []
        for start, end in windows:
            month = start.strftime("%Y-%m")
            if month in state.backfilled_months:
                continue
            try:
                fetched = await self._fetch_backfill_window(
                    symbol, company_name, start, end, failures
                )
            except QuotaExhaustedError as exc:
                # The daily budget is gone: every remaining window would fail the same way.
                log.warning("news_backfill_stopped", symbol=symbol, error=str(exc))
                return str(exc)
            if fetched is None:
                continue  # skipped now, retried on the next run
            await self._store(symbol, company_name, fetched)
            await self._repo.mark_month_done(symbol, month)
        now = self._clock()
        recent = NewsQuery(
            symbol=symbol,
            company_name=company_name,
            start=now - timedelta(days=INCREMENTAL_DAYS),
            end=now,
        )
        incremental_ok = True
        for provider in self._providers:
            try:
                items = await self._call(provider, recent)
            except ProviderError as exc:
                incremental_ok = False
                failures.append(str(exc))
                log.warning(
                    "news_window_failed", symbol=symbol, provider=provider.name, error=str(exc)
                )
                continue
            await self._store(symbol, company_name, items)
        if incremental_ok:
            await self._repo.mark_incremental(symbol, now)
        return "; ".join(failures[:3]) or None

    async def _call(self, provider: NewsProvider, query: NewsQuery) -> list[NewsItem]:
        """Guarded fetch that waits out a per-minute quota instead of skipping the window.

        Ingestion is a background job, so pausing is cheap. A daily quota error propagates.
        """
        for _ in range(MAX_QUOTA_WAITS):
            try:
                return await self._guard.call(provider.name, partial(provider.fetch, query))
            except QuotaExhaustedError as exc:
                if exc.window != "minute":
                    raise
                wait = MAX_QUOTA_WAIT
                if exc.retry_at is not None:
                    wait = min(
                        MAX_QUOTA_WAIT, max(0.0, (exc.retry_at - self._clock()).total_seconds())
                    )
                log.info(
                    "news_backfill_paused", provider=provider.name, wait_seconds=round(wait, 1)
                )
                await self._sleep(wait)
        return await self._guard.call(provider.name, partial(provider.fetch, query))

    async def _fetch_backfill_window(
        self,
        symbol: str,
        company_name: str,
        start: datetime,
        end: datetime,
        failures: list[str],
    ) -> list[NewsItem] | None:
        query = NewsQuery(symbol=symbol, company_name=company_name, start=start, end=end)
        items: list[NewsItem] = []
        found_provider = False
        for provider in self._providers:
            if provider.name != BACKFILL_PROVIDER:
                continue
            found_provider = True
            try:
                items += await self._call(provider, query)
            except QuotaExhaustedError as exc:
                if exc.window == "day":
                    raise
                failures.append(str(exc))
                return None
            except ProviderError as exc:
                failures.append(str(exc))
                log.warning(
                    "news_window_failed",
                    symbol=symbol,
                    provider=provider.name,
                    window=start.strftime("%Y-%m"),
                    error=str(exc),
                )
                return None
        return items if found_provider else None

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
        windows = self._windows(self._clock())
        done = sum(1 for w in windows if w[0].strftime("%Y-%m") in state.backfilled_months)
        return IngestProgress(done, len(windows), self._running(symbol))

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
                    f"months collected): {state.last_error or 'a source did not respond'}. "
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
