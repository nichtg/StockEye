"""Discover: curated lists of lesser-known stocks, built nightly and only ever read by users.

``refresh`` (the scheduled job) screens Yahoo once per preset, builds a full overview row for each
hit and stores the whole page in the cache. ``lists`` (the endpoint) reads that stored page and
never calls a vendor, so browsing Discover cannot spend any quota.

The build is deliberately slow and gentle: one row at a time, under the scheduled quota priority
(which waits out a per-minute block and leaves users headroom), so it never competes with them.
"""

import asyncio
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import AwareDatetime, BaseModel

from app.clock import utc_now
from app.db import Database
from app.logging_setup import get_logger
from app.providers.errors import ProviderError
from app.providers.models import CompanyProfile, ScreenMatch, ScreenQuery
from app.providers.quota import scheduled_calls
from app.repositories.cache import CacheRepository
from app.services.analysis import AnalysisService
from app.services.errors import AppError
from app.services.market_data import MarketDataService
from app.services.overview import WEEK_SESSIONS, OverviewRow, build_overview, profile_or_none
from app.services.status import DataStatus, combine, ok

log = get_logger(__name__)

CACHE_KEY = "discover:v2"
ATTEMPT_KEY = "discover:attempt:v2"
# The cron runs on weekdays only, so a page can legitimately be 3 days old over a weekend.
CACHE_TTL = timedelta(hours=74)
# A build is marked before it starts; a crash loop on startup then cannot re-run it for this long.
ATTEMPT_TTL = timedelta(hours=6)
SATURDAY = 5
BUILD_AT = (22, 30)  # UTC, weekdays: after the US close refresh
# A page is "overdue" only when the last scheduled build is this old and still has not landed.
BUILD_GRACE = timedelta(hours=1)
KEEP_STALE_FOR = timedelta(days=7)  # kept rows older than this are dropped rather than shown
# A failed build is retried this long afterwards, at most this many times per scheduled build.
# A retry rebuilds all three lists, not just the failed ones: bounded (3 retries) and accepted.
RETRY_DELAY = timedelta(minutes=45)
MAX_RETRIES = 3
ROWS_PER_LIST = 10
SCREEN_SIZE = 25  # the candidate pool: ranked first, then built in rank order until 10 rows
EMPTY_REASON = "Discover lists are being prepared. Check back in a few minutes."
_OVERDUE_REASON = "These lists did not refresh as scheduled. Showing the last saved version."
_PARTIAL_REASON = "Some stocks in this list could not be loaded tonight."
_FAILED_REASON = "This list could not be refreshed tonight. Showing the last saved version."
_NOTHING_REASON = "This list could not be built tonight."
# Closed-end funds sneak into Yahoo's equity screens (typeDisp and quoteType both say "Equity").
# Names that say "fund" or "ETF" are out. Yahoo files closed-end funds as "Asset Management" with
# no employees, so that industry is out when it has no headcount or the name reads like a fund
# vehicle; a real manager (Diamond Hill) has staff and an ordinary name, and stays. Banks and
# equity REITs named "... Trust" are real companies, so "trust" alone excludes nothing.
_FUND_NAME = re.compile(r"\b(fund|etf)\b", re.IGNORECASE)
_VEHICLE_NAME = re.compile(r"\b(trust|income|opportunit(y|ies)|municipal|portfolio|fund)\b", re.I)
_ASSET_MANAGEMENT = "Asset Management"

Rank = Literal["week_move", "pe", "traded_value"]


class DiscoverRow(OverviewRow):
    """A watchlist-style row plus the figures Discover ranks by (money in the row's currency)."""

    pe_ratio: float | None  # trailing twelve months
    avg_traded_value: float | None  # 3-month average daily volume x price


@dataclass(frozen=True)
class Preset:
    id: str
    title: str
    description: str
    order_label: str  # tells the reader how the rows are sorted
    query: ScreenQuery
    rank: Rank  # how candidates are ordered before any row is built
    exclude_funds: bool = False  # US lists only: Singapore REITs and trusts are real companies


PRESETS: tuple[Preset, ...] = (
    Preset(
        "us_small_movers",
        "Small caps on the move",
        "Smaller US companies with the biggest moves this week.",
        "Biggest 1-week move first",
        ScreenQuery(
            region="us",
            min_market_cap=300e6,
            max_market_cap=2e9,
            min_avg_volume=200_000,
            sort_field="dayvolume",
            sort_asc=False,
            size=SCREEN_SIZE,
        ),
        "week_move",
        exclude_funds=True,
    ),
    Preset(
        "us_value_small",
        "Lower-priced small caps",
        "Smaller US companies valued at under 15 times their earnings.",
        "Lowest price-to-earnings first",
        ScreenQuery(
            region="us",
            min_market_cap=300e6,
            max_market_cap=2e9,
            min_avg_volume=200_000,
            max_pe=15.0,
            sort_field="intradaymarketcap",
            sort_asc=False,
            size=SCREEN_SIZE,
        ),
        "pe",
        exclude_funds=True,
    ),
    Preset(
        "sg_under_radar",
        "Under the radar in Singapore",
        "Smaller Singapore-listed companies with steady trading.",
        "Most traded first",
        ScreenQuery(
            region="sg",
            min_market_cap=100e6,
            max_market_cap=3e9,
            min_avg_volume=50_000,
            sort_field="dayvolume",
            sort_asc=False,
            size=SCREEN_SIZE,
        ),
        "traded_value",
    ),
)


class DiscoverList(BaseModel):
    id: str
    title: str
    description: str
    order_label: str
    rows: list[DiscoverRow]
    status: DataStatus


class DiscoverOut(BaseModel):
    lists: list[DiscoverList]
    updated_at: AwareDatetime | None
    data_status: DataStatus


def last_scheduled_build(now: datetime) -> datetime:
    """The most recent weekday build time (22:30 UTC) at or before ``now``."""
    hour, minute = BUILD_AT
    at = now.astimezone(UTC).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if at > now:
        at -= timedelta(days=1)
    while at.weekday() >= SATURDAY:  # weekends have no build
        at -= timedelta(days=1)
    return at


def is_overdue(updated_at: datetime, now: datetime) -> bool:
    """Whether the build that should have landed by now (with a grace period) did not."""
    return updated_at < last_scheduled_build(now - BUILD_GRACE)


class DiscoverService:
    def __init__(
        self,
        db: Database,
        market: MarketDataService,
        analysis: AnalysisService,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._cache = CacheRepository(db)
        self._market = market
        self._analysis = analysis
        self._clock = clock
        self._lock = asyncio.Lock()  # one build at a time: a startup build can meet the cron job
        self._retry_hook: Callable[[datetime | None], None] | None = None
        self._retries = 0  # retries used since the last scheduled (non-retry) build

    def set_retry_hook(self, hook: Callable[[datetime | None], None]) -> None:
        """Let the scheduler own the retry job: called with a run time, or None to cancel it.

        A hook keeps this service free of any scheduler import, and keeps the retry bookkeeping
        (how many, how long to wait) here.
        """
        self._retry_hook = hook

    async def needs_startup_build(self) -> bool:
        """True when nothing useful is stored and no build was attempted lately (crash-loop guard).

        A stored page with no rows in any list counts as nothing: an empty build must not stick.
        """
        stored = await self._stored()
        if stored is not None and any(lst.rows for lst in stored.lists):
            return False
        marker = await self._cache.lookup(ATTEMPT_KEY)  # also returns expired entries
        return marker is None or not marker.is_fresh(self._clock())

    async def current_symbols(self) -> set[str]:
        """Every symbol on the stored page (so pruning keeps what Discover still shows)."""
        page = await self._stored()
        return {row.symbol for lst in page.lists for row in lst.rows} if page else set()

    async def refresh(self) -> None:
        """Rebuild every list and store the page. Never raises; a second call while one runs skips.

        A preset that fails keeps its previous rows, marked stale, and the others still update.
        Vendor calls draw on the quota reserved for scheduled work. A build where any list failed
        (or every list came out empty) queues a retry; see ``retry``.
        """
        await self._run_build(reset=True)

    async def retry(self) -> None:
        """A follow-up build after a failed one; at most ``MAX_RETRIES`` per scheduled build."""
        await self._run_build(reset=False)

    async def _run_build(self, *, reset: bool) -> None:
        if self._lock.locked():
            log.info("discover_refresh_skipped", reason="a build is already running")
            return
        async with self._lock:
            if reset:  # only once the build really runs: a skipped call must not refill the cap
                self._retries = 0
            with scheduled_calls():
                try:
                    healthy = await self._refresh()
                except Exception:
                    log.exception("discover_refresh_failed")
                    healthy = False
            self._plan_retry(healthy)

    def _plan_retry(self, healthy: bool) -> None:
        """Cancel any pending retry after a good build; else queue the next, up to the cap."""
        if self._retry_hook is None:
            return
        try:
            if healthy:
                self._retry_hook(None)
            elif self._retries < MAX_RETRIES:
                self._retries += 1
                self._retry_hook(self._clock() + RETRY_DELAY)
            else:
                self._retry_hook(None)
                log.warning("discover_retries_exhausted", retries=MAX_RETRIES)
        except Exception:  # the scheduler must never break a build
            log.exception("discover_retry_schedule_failed")

    async def _refresh(self) -> bool:
        """Build and store the page; True when every list built and at least one has rows."""
        now = self._clock()
        await self._cache.put(ATTEMPT_KEY, {"at": now.isoformat()}, ATTEMPT_TTL, now)
        previous = await self._stored()
        old = {lst.id: lst for lst in previous.lists} if previous else {}
        lists: list[DiscoverList] = []
        failed = False
        for preset in PRESETS:
            built, built_ok = await self._build(preset, old.get(preset.id), now)
            lists.append(built)
            failed = failed or not built_ok
        page = DiscoverOut(
            lists=lists, updated_at=now, data_status=combine([lst.status for lst in lists])
        )
        await self._cache.put(CACHE_KEY, page.model_dump(mode="json"), CACHE_TTL, now)
        log.info("discover_refresh_finished", rows=[len(lst.rows) for lst in lists])
        return not failed and any(lst.rows for lst in lists)

    async def lists(self) -> DiscoverOut:
        """The stored page. Reads the cache only: it never calls a vendor."""
        page = await self._stored()
        if page is None:
            return DiscoverOut(
                lists=[],
                updated_at=None,
                data_status=DataStatus(state="unavailable", reason=EMPTY_REASON),
            )
        if page.updated_at is not None and is_overdue(page.updated_at, self._clock()):
            late = DataStatus(state="stale", as_of=page.updated_at, reason=_OVERDUE_REASON)
            page = page.model_copy(update={"data_status": combine([page.data_status, late])})
        return page

    async def _stored(self) -> DiscoverOut | None:
        entry = await self._cache.lookup(CACHE_KEY)
        return entry.parse(DiscoverOut) if entry is not None else None

    async def _build(
        self, preset: Preset, old: DiscoverList | None, now: datetime
    ) -> tuple[DiscoverList, bool]:
        """The list to store, and whether building it worked (False: old rows kept, or none)."""
        try:
            rows, complete = await self._rows(preset)
        except Exception as exc:
            if isinstance(exc, AppError | ProviderError):
                log.warning(
                    "discover_preset_failed",
                    preset=preset.id,
                    error=type(exc).__name__,
                    detail=exc.message if isinstance(exc, AppError) else str(exc),
                )
            else:
                log.exception("discover_preset_failed", preset=preset.id)
            return _kept(preset, old, now), False
        status = (
            ok(now) if complete else DataStatus(state="stale", as_of=now, reason=_PARTIAL_REASON)
        )
        built = DiscoverList(
            id=preset.id,
            title=preset.title,
            description=preset.description,
            order_label=preset.order_label,
            rows=rows,
            status=status,
        )
        return built, True

    async def _rows(self, preset: Preset) -> tuple[list[DiscoverRow], bool]:
        """The top ``ROWS_PER_LIST`` hits by the preset's own order; and whether none was lost.

        Candidates are ranked first (from the screener's figures, or one cached history call for
        the movers list) and rows are then built in rank order, one at a time, until the list is
        full, so a build is never spent on a stock that would not make the cut. Raises when the
        screen fails, or when it found rankable hits but none could be built (a vendor problem,
        not an empty market).
        """
        matches = await self._market.screen(preset.query)
        pool = [m for m in matches if not (preset.exclude_funds and _is_fund(m, None))]
        ranked = await self._ranked(preset, pool)
        funds = 0  # profile-detected funds are not candidates, so they cannot make a list stale
        built: list[DiscoverRow] = []
        for match in ranked:
            if len(built) == ROWS_PER_LIST:
                break
            # The profile is cached for a day and the row build reuses it: a fund costs one call.
            if preset.exclude_funds and _is_fund(
                match, await profile_or_none(self._market, match.symbol)
            ):
                funds += 1
                continue
            # One row at a time: each costs about 3 vendor calls, and a burst would eat the
            # per-minute allowance users need.
            (row,) = await build_overview(
                self._market, self._analysis, [match.symbol], concurrency=1
            )
            if row.status != "unavailable":
                built.append(_discover_row(row, match))
        wanted = len(ranked) - funds
        if wanted and not built:
            raise AppError(503, "data_unavailable", "No stock in the list could be loaded.")
        return built, len(built) >= min(ROWS_PER_LIST, wanted)

    async def _ranked(self, preset: Preset, pool: list[ScreenMatch]) -> list[ScreenMatch]:
        """Rankable candidates, best first (stable on ties); the rest are left out."""
        keyed: list[tuple[float, ScreenMatch]] = []
        for match in pool:
            key = await self._rank_key(preset.rank, match)
            if key is not None:
                keyed.append((key, match))
        keyed.sort(key=lambda pair: pair[0])
        return [m for _, m in keyed]

    async def _rank_key(self, rank: Rank, match: ScreenMatch) -> float | None:
        """Smaller sorts first; None means this hit cannot be ranked and is left out."""
        if rank == "pe":
            return match.pe_ratio if match.pe_ratio is not None and match.pe_ratio > 0 else None
        if rank == "traded_value":
            # Only SGD lines: a USD-quoted SGX line's value would not compare with the others.
            value = _traded_value(match)
            return -value if value is not None and match.currency == "SGD" else None
        move = await self._week_move(match.symbol)
        return -abs(move) if move is not None else math.inf  # unknown 1-week move sorts last

    async def _week_move(self, symbol: str) -> float | None:
        """1-week change in percent from the shared daily history (the row build reuses it)."""
        try:
            frame, _ = await self._market.daily_history(symbol)
        except (AppError, ProviderError):
            return None
        closes = [float(c) for c in frame["close"].tolist()]
        if len(closes) <= WEEK_SESSIONS or not closes[-1 - WEEK_SESSIONS]:
            return None
        return (closes[-1] / closes[-1 - WEEK_SESSIONS] - 1.0) * 100.0


def _is_fund(match: ScreenMatch, profile: CompanyProfile | None) -> bool:
    """Closed-end funds and similar; ``profile`` None means only the name can be judged."""
    if _FUND_NAME.search(match.name):
        return True
    if profile is None or profile.industry != _ASSET_MANAGEMENT:
        return False
    return profile.employees is None or bool(_VEHICLE_NAME.search(match.name))


def _traded_value(match: ScreenMatch) -> float | None:
    """3-month average daily volume x price, in the quote currency."""
    if match.avg_volume_3m is None or match.price is None:
        return None
    return match.avg_volume_3m * match.price


def _kept(preset: Preset, old: DiscoverList | None, now: datetime) -> DiscoverList:
    """The list to store when building it failed: the old rows marked stale, else an empty list."""
    as_of = old.status.as_of if old is not None else None
    if old is None or not old.rows or as_of is None or now - as_of > KEEP_STALE_FOR:
        return DiscoverList(
            id=preset.id,
            title=preset.title,
            description=preset.description,
            order_label=preset.order_label,
            rows=[],
            status=DataStatus(state="unavailable", reason=_NOTHING_REASON),
        )
    return old.model_copy(
        update={
            "title": preset.title,
            "description": preset.description,
            "order_label": preset.order_label,
            "status": DataStatus(state="stale", as_of=as_of, reason=_FAILED_REASON),
        }
    )


def _discover_row(row: OverviewRow, match: ScreenMatch) -> DiscoverRow:
    """Add the ranking figures, and fill a missing market cap from the screener hit."""
    cap = row.market_cap if row.market_cap is not None else match.market_cap
    return DiscoverRow.model_validate(
        row.model_dump()
        | {"market_cap": cap, "pe_ratio": match.pe_ratio, "avg_traded_value": _traded_value(match)}
    )
