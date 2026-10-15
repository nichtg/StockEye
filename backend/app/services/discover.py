"""Discover: curated lists of lesser-known stocks, built nightly and only ever read by users.

``refresh`` (the scheduled job) screens Yahoo once per preset, builds a full overview row for each
hit and stores the whole page in the cache. ``lists`` (the endpoint) reads that stored page and
never calls a vendor, so browsing Discover cannot spend any quota.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from pydantic import AwareDatetime, BaseModel

from app.clock import utc_now
from app.db import Database
from app.logging_setup import get_logger
from app.providers.base import MarketDataProvider
from app.providers.errors import ProviderError
from app.providers.models import ScreenMatch, ScreenQuery
from app.providers.quota import scheduled_calls
from app.repositories.cache import CacheRepository
from app.services.analysis import AnalysisService
from app.services.market_data import MarketDataService
from app.services.overview import OverviewRow, build_overview
from app.services.status import DataStatus, combine, describe_failure, ok

log = get_logger(__name__)

CACHE_KEY = "discover:v1"
# Longer than a day so one missed nightly run does not blank the page; stale is acceptable.
CACHE_TTL = timedelta(hours=26)
ROWS_PER_LIST = 15
EMPTY_REASON = "Discover lists are being prepared. Check back in a few minutes."
_STALE_AGE_REASON = "These lists did not refresh overnight. Showing the last saved version."


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
            size=ROWS_PER_LIST,
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
            size=ROWS_PER_LIST,
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
            size=ROWS_PER_LIST,
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


class DiscoverService:
    def __init__(
        self,
        db: Database,
        provider: MarketDataProvider,
        market: MarketDataService,
        analysis: AnalysisService,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._cache = CacheRepository(db)
        self._provider = provider
        self._market = market
        self._analysis = analysis
        self._clock = clock

    async def has_lists(self) -> bool:
        """Whether a built page is stored (even an old one)."""
        return await self._stored() is not None

    async def refresh(self) -> None:
        """Rebuild every list and store the page. Never raises.

        A preset that fails keeps its previous rows, marked stale, and the others still update.
        Vendor calls draw on the quota reserved for scheduled work.
        """
        with scheduled_calls():
            try:
                previous = await self._stored()
                old = {lst.id: lst for lst in previous.lists} if previous else {}
                now = self._clock()
                lists = [await self._build(preset, old.get(preset.id), now) for preset in PRESETS]
                page = DiscoverOut(
                    lists=lists,
                    updated_at=now,
                    data_status=combine([lst.status for lst in lists]),
                )
                await self._cache.put(CACHE_KEY, page.model_dump(mode="json"), CACHE_TTL, now)
            except Exception:
                log.exception("discover_refresh_failed")
                return
        log.info("discover_refresh_finished", rows=[len(lst.rows) for lst in lists])

    async def lists(self) -> DiscoverOut:
        """The stored page. Reads the cache only: it never calls a vendor."""
        entry = await self._cache.lookup(CACHE_KEY)
        page = entry.parse(DiscoverOut) if entry is not None else None
        if entry is None or page is None:
            return DiscoverOut(
                lists=[],
                updated_at=None,
                data_status=DataStatus(state="unavailable", reason=EMPTY_REASON),
            )
        if not entry.is_fresh(self._clock()):
            late = DataStatus(state="stale", as_of=page.updated_at, reason=_STALE_AGE_REASON)
            page = page.model_copy(update={"data_status": combine([page.data_status, late])})
        return page

    async def _stored(self) -> DiscoverOut | None:
        entry = await self._cache.lookup(CACHE_KEY)
        return entry.parse(DiscoverOut) if entry is not None else None

    async def _build(self, preset: Preset, old: DiscoverList | None, now: datetime) -> DiscoverList:
        try:
            rows = await self._rows(preset)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("discover_preset_failed", preset=preset.id, error=repr(exc))
            return _kept(preset, old, now, exc)
        return DiscoverList(
            id=preset.id,
            title=preset.title,
            description=preset.description,
            rows=rows,
            status=ok(now),
        )

    async def _rows(self, preset: Preset) -> list[OverviewRow]:
        matches = (await self._provider.screen(preset.query))[:ROWS_PER_LIST]
        built = await build_overview(self._market, self._analysis, [m.symbol for m in matches])
        rows = [
            _with_cap(row, match)
            for row, match in zip(built, matches, strict=True)
            if row.status != "unavailable"
        ]
        if matches and not rows:
            # Every hit failed: that is a vendor problem, not an empty market.
            raise ProviderError("yahoo", "no row of the list could be built")
        return rows


def _kept(preset: Preset, old: DiscoverList | None, now: datetime, exc: Exception) -> DiscoverList:
    """The list to store when building it failed: the old rows marked stale, else an empty list."""
    cause = describe_failure(exc) if isinstance(exc, ProviderError) else "something went wrong"
    if old is None or not old.rows:
        return DiscoverList(
            id=preset.id,
            title=preset.title,
            description=preset.description,
            rows=[],
            status=DataStatus(
                state="unavailable", reason=f"This list could not be built: {cause}."
            ),
        )
    reason = f"This list could not be refreshed: {cause}. Showing the last saved version."
    return old.model_copy(
        update={
            "title": preset.title,
            "description": preset.description,
            "status": DataStatus(state="stale", as_of=old.status.as_of or now, reason=reason),
        }
    )


def _with_cap(row: OverviewRow, match: ScreenMatch) -> OverviewRow:
    """Fill a missing market cap from the screener hit (the profile call may have failed)."""
    if row.market_cap is None and match.market_cap is not None:
        return row.model_copy(update={"market_cap": match.market_cap})
    return row
