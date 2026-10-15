"""Discover: curated lists of lesser-known stocks, built nightly and only ever read by users.

``refresh`` (the scheduled job) screens Yahoo once per preset, builds a full overview row for each
hit and stores the whole page in the cache. ``lists`` (the endpoint) reads that stored page and
never calls a vendor, so browsing Discover cannot spend any quota.

The build is deliberately slow and gentle: one row at a time, under the scheduled quota priority
(which waits out a per-minute block and leaves users headroom), so it never competes with them.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pydantic import AwareDatetime, BaseModel

from app.clock import utc_now
from app.db import Database
from app.logging_setup import get_logger
from app.providers.errors import ProviderError
from app.providers.models import ScreenMatch, ScreenQuery
from app.providers.quota import scheduled_calls
from app.repositories.cache import CacheRepository
from app.services.analysis import AnalysisService
from app.services.errors import AppError
from app.services.market_data import MarketDataService
from app.services.overview import OverviewRow, build_overview
from app.services.status import DataStatus, combine, ok

log = get_logger(__name__)

CACHE_KEY = "discover:v1"
ATTEMPT_KEY = "discover:attempt"
# The cron runs on weekdays only, so a page can legitimately be 3 days old over a weekend.
CACHE_TTL = timedelta(hours=74)
# A build is marked before it starts; a crash loop on startup then cannot re-run it for this long.
ATTEMPT_TTL = timedelta(hours=6)
SATURDAY = 5
BUILD_AT = (22, 30)  # UTC, weekdays: after the US close refresh
# A page is "overdue" only when the last scheduled build is this old and still has not landed.
BUILD_GRACE = timedelta(hours=1)
KEEP_STALE_FOR = timedelta(days=7)  # kept rows older than this are dropped rather than shown
ROWS_PER_LIST = 15
SCREEN_SIZE = 25  # ask for more than we show, so a few unbuildable hits do not thin a list
EMPTY_REASON = "Discover lists are being prepared. Check back in a few minutes."
_OVERDUE_REASON = "These lists did not refresh as scheduled. Showing the last saved version."
_PARTIAL_REASON = "Some stocks in this list could not be loaded tonight."
_FAILED_REASON = "This list could not be refreshed tonight. Showing the last saved version."
_NOTHING_REASON = "This list could not be built tonight."


@dataclass(frozen=True)
class Preset:
    id: str
    title: str
    description: str
    query: ScreenQuery


PRESETS: tuple[Preset, ...] = (
    Preset(
        "us_small_movers",
        "Small caps on the move",
        "Smaller US companies whose shares moved most today.",
        ScreenQuery(
            region="us",
            min_market_cap=300e6,
            max_market_cap=2e9,
            min_avg_volume=200_000,
            sort_field="percentchange",
            sort_asc=False,
            size=SCREEN_SIZE,
        ),
    ),
    Preset(
        "us_value_small",
        "Lower-priced small caps",
        "Smaller US companies valued at under 15 times their earnings.",
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
    ),
    Preset(
        "sg_under_radar",
        "Under the radar in Singapore",
        "Smaller Singapore-listed companies with steady trading.",
        ScreenQuery(
            region="sg",
            min_market_cap=100e6,
            max_market_cap=3e9,
            min_avg_volume=50_000,
            sort_field="dayvolume",
            sort_asc=False,
            size=SCREEN_SIZE,
        ),
    ),
)


class DiscoverList(BaseModel):
    id: str
    title: str
    description: str
    rows: list[OverviewRow]
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

    async def needs_startup_build(self) -> bool:
        """True when nothing is stored and no build was attempted lately (crash-loop guard)."""
        if await self._stored() is not None:
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
        Vendor calls draw on the quota reserved for scheduled work.
        """
        if self._lock.locked():
            log.info("discover_refresh_skipped", reason="a build is already running")
            return
        async with self._lock:
            with scheduled_calls():
                try:
                    await self._refresh()
                except Exception:
                    log.exception("discover_refresh_failed")

    async def _refresh(self) -> None:
        now = self._clock()
        await self._cache.put(ATTEMPT_KEY, {"at": now.isoformat()}, ATTEMPT_TTL, now)
        previous = await self._stored()
        old = {lst.id: lst for lst in previous.lists} if previous else {}
        lists = [await self._build(preset, old.get(preset.id), now) for preset in PRESETS]
        page = DiscoverOut(
            lists=lists, updated_at=now, data_status=combine([lst.status for lst in lists])
        )
        await self._cache.put(CACHE_KEY, page.model_dump(mode="json"), CACHE_TTL, now)
        log.info("discover_refresh_finished", rows=[len(lst.rows) for lst in lists])

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

    async def _build(self, preset: Preset, old: DiscoverList | None, now: datetime) -> DiscoverList:
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
            return _kept(preset, old, now)
        status = (
            ok(now) if complete else DataStatus(state="stale", as_of=now, reason=_PARTIAL_REASON)
        )
        return DiscoverList(
            id=preset.id,
            title=preset.title,
            description=preset.description,
            rows=rows,
            status=status,
        )

    async def _rows(self, preset: Preset) -> tuple[list[OverviewRow], bool]:
        """The first ``ROWS_PER_LIST`` hits that build, one at a time; and whether none was lost.

        Raises when the screen fails, or when it found hits but none of them could be built (a
        vendor problem, not an empty market).
        """
        matches = await self._market.screen(preset.query)
        rows: list[OverviewRow] = []
        for match in matches:
            if len(rows) == ROWS_PER_LIST:
                break
            # One row at a time: each costs about 3 vendor calls, and a burst would eat the
            # per-minute allowance users need.
            (row,) = await build_overview(
                self._market, self._analysis, [match.symbol], concurrency=1
            )
            if row.status != "unavailable":
                rows.append(_with_cap(row, match))
        if matches and not rows:
            raise AppError(503, "data_unavailable", "No stock in the list could be loaded.")
        return rows, len(rows) >= min(ROWS_PER_LIST, len(matches))


def _kept(preset: Preset, old: DiscoverList | None, now: datetime) -> DiscoverList:
    """The list to store when building it failed: the old rows marked stale, else an empty list."""
    as_of = old.status.as_of if old is not None else None
    if old is None or not old.rows or as_of is None or now - as_of > KEEP_STALE_FOR:
        return DiscoverList(
            id=preset.id,
            title=preset.title,
            description=preset.description,
            rows=[],
            status=DataStatus(state="unavailable", reason=_NOTHING_REASON),
        )
    return old.model_copy(
        update={
            "title": preset.title,
            "description": preset.description,
            "status": DataStatus(state="stale", as_of=as_of, reason=_FAILED_REASON),
        }
    )


def _with_cap(row: OverviewRow, match: ScreenMatch) -> OverviewRow:
    """Fill a missing market cap from the screener hit (the profile call may have failed)."""
    if row.market_cap is None and match.market_cap is not None:
        return row.model_copy(update={"market_cap": match.market_cap})
    return row
