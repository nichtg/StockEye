"""Map news timestamps onto the trading session whose price could first react to them.

Look-ahead rule: an article is attributed to the first session whose close is strictly after
its publication time, never to a session that had already closed. News published at or after
the close (or on a weekend or holiday) therefore lands on the next session.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd


@dataclass(frozen=True)
class ScoredArticle:
    """One news article with a sentiment ``score`` in [-1, 1] and a tz-aware ``published_at``."""

    published_at: datetime
    score: float
    title: str
    url: str
    source: str


@dataclass(frozen=True)
class SessionCalendar:
    """Trading sessions and their tz-aware UTC close times, both strictly increasing."""

    sessions: tuple[date, ...]
    closes_utc: tuple[datetime, ...]

    def __post_init__(self) -> None:
        if len(self.sessions) != len(self.closes_utc):
            raise ValueError("sessions and closes_utc must have equal length")
        if any(c.tzinfo is None for c in self.closes_utc):
            raise ValueError("closes_utc must be timezone-aware")
        if any(b <= a for a, b in zip(self.sessions, self.sessions[1:], strict=False)):
            raise ValueError("sessions must be strictly increasing")
        if any(b <= a for a, b in zip(self.closes_utc, self.closes_utc[1:], strict=False)):
            raise ValueError("closes_utc must be strictly increasing")


def effective_session(published_at: datetime, cal: SessionCalendar) -> date | None:
    """First session whose close is strictly after ``published_at``; None if there is none.

    Raises ValueError for a naive datetime, because its meaning would be ambiguous.
    """
    if published_at.tzinfo is None or published_at.utcoffset() is None:
        raise ValueError("published_at must be timezone-aware")
    idx = bisect_right(cal.closes_utc, published_at)
    if idx >= len(cal.sessions):
        return None
    return cal.sessions[idx]


_COLUMNS = ["mean_score", "article_count", "max_abs_score"]


def daily_sentiment(
    articles: Sequence[ScoredArticle], cal: SessionCalendar
) -> tuple[pd.DataFrame, dict[date, list[ScoredArticle]]]:
    """Aggregate article scores per effective session.

    Returns ``(frame, by_session)``. The frame is indexed by naive session Timestamp with
    ``mean_score``, ``article_count`` and ``max_abs_score``. Sessions without news are absent
    (not zero): silence is not neutral sentiment. ``by_session`` keeps the articles per session
    so headlines can be shown. Articles with no later session are dropped.
    """
    by_session: dict[date, list[ScoredArticle]] = defaultdict(list)
    for art in articles:
        session = effective_session(art.published_at, cal)
        if session is not None:
            by_session[session].append(art)

    sessions = sorted(by_session)
    rows = [
        (
            sum(a.score for a in by_session[s]) / len(by_session[s]),
            len(by_session[s]),
            max(abs(a.score) for a in by_session[s]),
        )
        for s in sessions
    ]
    frame = pd.DataFrame(
        rows,
        index=pd.DatetimeIndex([pd.Timestamp(s) for s in sessions]),
        columns=pd.Index(_COLUMNS),
    )
    frame["article_count"] = frame["article_count"].astype(int)
    return frame, {s: by_session[s] for s in sessions}
