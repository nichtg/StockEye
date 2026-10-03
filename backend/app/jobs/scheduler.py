"""APScheduler wiring: two weekday refreshes, one per exchange, shortly after each close."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.db import Database
from app.jobs.ingest import refresh_exchange
from app.providers.models import Exchange
from app.services.container import Services

# US closes 20:00-21:00 UTC depending on daylight saving, SGX closes 09:00 UTC.
SCHEDULE: dict[Exchange, tuple[int, int]] = {"US": (21, 30), "SGX": (9, 30)}


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
    return scheduler
