"""Keeping the news collection lean: trim at ingest, and tidy what is already stored.

* ``trim_items`` runs on every fetched batch: it drops low-value items and splits off same-day
  near-duplicates of articles already kept for the symbol (or earlier in the batch).
* ``backfill_stored_news`` is the one-off, idempotent startup pass: flag old documents, then fold
  stored near-duplicates the same way (per symbol, with a marker in the ingest state).

Both reuse the Phase 7 story rule through ``domain.news``; nothing here loosens it.
"""

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from app.db import Database
from app.domain.macro import is_price_recap
from app.domain.news import (
    Story,
    fold_near_duplicates,
    ignore_tokens,
    is_low_value,
    shared_words,
)
from app.logging_setup import get_logger
from app.providers.models import NewsItem
from app.repositories.news import NewsRepository, dedupe_key
from app.repositories.news_maintenance import (
    NewsMaintenanceRepository,
    SimilarEntry,
    similar_entry,
)
from app.services.calendars import exchange_tz, root_ticker

log = get_logger(__name__)

DEDUPE_VERSION = 1  # bump to fold stored articles again after the similarity rule changes
FOLD_BATCH = 200


@dataclass(frozen=True)
class Trimmed:
    """What to do with one fetched batch."""

    keep: list[NewsItem]  # upsert these
    folds: dict[str, list[SimilarEntry]]  # kept article key -> its new duplicates
    low_value: int  # items dropped as low-value

    @property
    def folded(self) -> int:
        return sum(len(entries) for entries in self.folds.values())


async def trim_items(
    repo: NewsRepository, symbol: str, company_name: str, items: list[NewsItem]
) -> Trimmed:
    """Drop low-value items and fold same-day near-duplicates (exchange-local day).

    A folded item is not stored for ``symbol``; it is recorded on the article that was kept.
    Articles are shared across symbols, so the same item may still be stored for another
    symbol, where nothing like it is kept that day. Price recaps are never folded (they are
    hidden from the feed), and neither are stored recaps or low-value documents used as
    targets, so nothing disappears behind a hidden article. Items already stored for
    ``symbol`` (any day) are re-fetches, not duplicates.
    """
    newsworthy = [i for i in items if not is_low_value(i.title)]
    low_value = len(items) - len(newsworthy)
    fresh = {dedupe_key(i.title, i.source): i for i in newsworthy if not is_price_recap(i.title)}
    known = await repo.existing_keys(symbol, list(fresh))
    candidates = {k: i for k, i in fresh.items() if k not in known}
    if not candidates:
        return Trimmed(newsworthy, {}, low_value)
    tz = exchange_tz(symbol)
    days = [i.published_at.astimezone(tz).date() for i in candidates.values()]
    start = datetime.combine(min(days), time.min, tzinfo=tz).astimezone(UTC)
    end = datetime.combine(max(days) + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
    stored = [
        s
        for s in await repo.stories_between(symbol, start, end)
        if not is_price_recap(s.title) and not is_low_value(s.title)
    ]
    new = [Story(key, i.title, i.published_at) for key, i in candidates.items()]
    folded = fold_near_duplicates(new, stored, tz, ignore_tokens(symbol, company_name))
    folds: dict[str, list[SimilarEntry]] = {}
    for key, main in folded.items():
        folds.setdefault(main, []).append(similar_entry(candidates[key]))
    keep = [i for i in newsworthy if dedupe_key(i.title, i.source) not in folded]
    return Trimmed(keep, folds, low_value)


@dataclass(frozen=True)
class BackfillSummary:
    flagged: int  # documents that got the flags
    folded: int  # stored duplicates moved into a kept article's similar list


async def backfill_stored_news(
    db: Database,
    *,
    company_name: Callable[[str], Awaitable[str]] | None = None,
    is_running: Callable[[str], bool] = lambda _symbol: False,
) -> BackfillSummary:
    """Flag documents that predate the flags, then fold stored near-duplicates, per symbol.

    One-off and idempotent: a second run updates nothing. Resumable: a symbol is marked
    (``dedupe_version`` in the ingest state) only once all its folds are done, and a fold is
    recorded on the kept article before the duplicate is removed, so a crash in between just
    repeats safely. Never raises; a failing symbol is logged and skipped. Run it in the
    background (it can take a while on a large collection). It can be dropped once every
    deployment has run it.

    ``company_name`` (the lookup the feed uses) gives the real name for the similarity rule;
    without one, or when it only returns the ticker, the shared words stand in. A symbol being
    ingested right now (``is_running``) is skipped and left unmarked, so the next startup
    retries it.
    """
    maint = NewsMaintenanceRepository(db)
    flagged = folded = 0
    try:
        flagged = await maint.backfill_flags()
        for symbol in await maint.symbols_to_dedupe(DEDUPE_VERSION):
            if is_running(symbol):
                continue
            try:
                name = await _name_of(company_name, symbol)
                folded += await dedupe_stored(maint, symbol, name, is_running)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("news_dedupe_backfill_symbol_failed", symbol=symbol)
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("news_backfill_failed")
    log.info("news_backfill_finished", flagged=flagged, folded=folded)
    return BackfillSummary(flagged, folded)


async def _name_of(lookup: Callable[[str], Awaitable[str]] | None, symbol: str) -> str | None:
    """The company name, or None when there is no lookup, it fails, or it only gives the ticker."""
    if lookup is None:
        return None
    try:
        name = (await lookup(symbol)).strip()
    except asyncio.CancelledError:
        raise
    except Exception:
        return None
    return None if not name or name.upper() == root_ticker(symbol).upper() else name


async def dedupe_stored(
    maint: NewsMaintenanceRepository,
    symbol: str,
    company_name: str | None = None,
    is_running: Callable[[str], bool] = lambda _symbol: False,
) -> int:
    """Fold the stored near-duplicates of ``symbol`` (earliest of a day stays) and mark it done.

    With a ``company_name`` the similarity rule is exactly the ingest one; without, the words
    most headlines share stand in for it (``shared_words``). Folding runs one exchange-local
    day at a time (a story only matches within its day) and yields to the event loop between
    days, so a big symbol never blocks a small server. A duplicate's own recorded look-alikes
    move to the kept article with it. The duplicate loses ``symbol``
    and is deleted when no other symbol holds it. Returns how many were folded.
    """
    articles = [
        a
        for a in await maint.showable_articles(symbol)
        if not is_price_recap(a.title) and not is_low_value(a.title)
    ]
    if company_name is not None:
        ignore = ignore_tokens(symbol, company_name)
    else:
        ignore = ignore_tokens(symbol, "") | shared_words([a.title for a in articles])
    tz = exchange_tz(symbol)
    days: defaultdict[object, list[Story]] = defaultdict(list)
    for a in articles:
        days[a.published_at.astimezone(tz).date()].append(Story(a.key, a.title, a.published_at))
    mapping: dict[str, str] = {}
    for day_stories in days.values():
        mapping.update(fold_near_duplicates(day_stories, [], tz, ignore))
        await asyncio.sleep(0)  # let requests and ingestion run between days
    if is_running(symbol):  # ingestion started meanwhile: leave it, unmarked, for next startup
        return 0
    by_key = {a.key: a for a in articles}
    items = list(mapping.items())
    for start in range(0, len(items), FOLD_BATCH):
        chunk = items[start : start + FOLD_BATCH]
        folds: dict[str, list[SimilarEntry]] = {}
        for key, main in chunk:
            duplicate = by_key[key]
            folds.setdefault(main, []).extend([duplicate.as_entry(), *duplicate.similar])
        await maint.add_similar(folds)
        await maint.unlink_symbol(symbol, [key for key, _ in chunk])
    await maint.mark_deduped(symbol, DEDUPE_VERSION)
    return len(mapping)
