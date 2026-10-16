"""Which newly fetched articles duplicate one already kept (pure).

Reuses the Phase 7 story rule (``cluster_stories``) unchanged; this module only decides who is
compared with whom at ingest: same exchange-local day, stored articles first.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from app.domain.news.similarity import cluster_stories


@dataclass(frozen=True)
class Story:
    """One headline: ``key`` is the article's dedupe key, ``published_at`` is timezone-aware."""

    key: str
    title: str
    published_at: datetime


def fold_near_duplicates(
    new: Sequence[Story],
    stored: Sequence[Story],
    tz: ZoneInfo,
    ignore: Collection[str] = (),
) -> dict[str, str]:
    """Map each duplicate new story's key to the key of the article that stays the main one.

    A new story folds into a ``stored`` article, or into an earlier new story, when the two
    were published on the same ``tz`` day and ``cluster_stories`` calls them near-duplicates.
    The stored article always stays the main one (the earliest of them); among new stories the
    earliest published stays (ties by key, so the outcome never depends on fetch order).
    Stories whose key is already stored, or repeated within ``new``, are not duplicates of
    anything: they are left out of the result (the caller upserts them as usual). ``ignore``
    holds company-name and ticker words every headline shares.
    """
    stored = sorted(stored, key=lambda s: (s.published_at, s.key))  # a deterministic head
    stored_keys = {s.key for s in stored}
    fresh: dict[str, Story] = {}
    for story in sorted(new, key=lambda s: (s.published_at, s.key)):
        if story.key not in stored_keys:
            fresh.setdefault(story.key, story)
    ordered = [*stored, *fresh.values()]
    items = [(s.published_at.astimezone(tz).date(), s.title) for s in ordered]
    folded: dict[str, str] = {}
    for group in cluster_stories(items, ignore):
        head = ordered[group[0]]
        for index in group[1:]:
            if index >= len(stored):  # stored members are already stored; leave them be
                folded[ordered[index].key] = head.key
    return folded
