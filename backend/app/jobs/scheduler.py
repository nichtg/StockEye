"""APScheduler wiring: weekday refreshes after each close, then the nightly Discover rebuild."""

from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from app.clock import utc_now
from app.db import Database
from app.jobs.ingest import refresh_exchange
from app.providers.models import Exchange
from app.services.container import Services

# US closes 20:00-21:00 UTC depending on daylight saving, SGX closes 09:00 UTC.
SCHEDULE: dict[Exchange, tuple[int, int]] = {"US": (21, 30), "SGX": (9, 30)}
# After the US refresh, so the screener sees the closing prices.
DISCOVER_AT = (22, 30)
DISCOVER_JOB_ID = "discover_refresh"
STARTUP_DISCOVER_JOB_ID = "discover_startup"
STARTUP_DISCOVER_DELAY = timedelta(seconds=60)


def build_scheduler(services: Services, db: Database) -> AsyncIOScheduler:
    """A scheduler (not yet started) with one refresh job per exchange, weekdays, UTC."""
    scheduler = AsyncIOScheduler(timezone="UTC")
    for exchange, (hour, minute) in SCHEDULE.items():
        scheduler.add_job(
            refresh_exchange,
            CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute, timezone="UTC"),
            args=[services, db, exchange],
            id=f"refresh_{exchange.lower()}",
            max_instances=1,  # a slow run must not overlap the next
            coalesce=True,
            misfire_grace_time=3600,
            replace_existing=True,
        )
    hour, minute = DISCOVER_AT
    scheduler.add_job(
        services.discover.refresh,
        CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute, timezone="UTC"),
        id=DISCOVER_JOB_ID,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
        replace_existing=True,
    )
    return scheduler


async def schedule_startup_discover(scheduler: AsyncIOScheduler, services: Services) -> bool:
    """Queue one background Discover build shortly after start when none is stored yet.

    Never inline: the build takes minutes and must not hold up startup or a request.
    """
    if await services.discover.has_lists():
        return False
    scheduler.add_job(
        services.discover.refresh,
        DateTrigger(run_date=utc_now() + STARTUP_DISCOVER_DELAY, timezone="UTC"),
        id=STARTUP_DISCOVER_JOB_ID,
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    return True
