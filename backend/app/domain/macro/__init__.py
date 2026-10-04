"""Macro analysis: news-sentiment event study over a 2-year horizon (pure, no I/O)."""

from app.domain.macro.alignment import (
    ScoredArticle,
    SessionCalendar,
    daily_sentiment,
    effective_session,
)
from app.domain.macro.event_study import EventResult, run_event_study, select_events
from app.domain.macro.sentiment_stats import (
    BucketStats,
    Correlation,
    Difference,
    MacroStats,
    Regime,
    TimelinePoint,
    bucket_of,
    compute_stats,
    reliability_label,
    sentiment_regime,
    weekly_timeline,
)
from app.domain.macro.summary import (
    EventPoint,
    Finding,
    Headline,
    MacroReport,
    TopEvent,
    build_macro_report,
)

__all__ = [
    "BucketStats",
    "Correlation",
    "Difference",
    "EventPoint",
    "EventResult",
    "Finding",
    "Headline",
    "MacroReport",
    "MacroStats",
    "Regime",
    "ScoredArticle",
    "SessionCalendar",
    "TimelinePoint",
    "TopEvent",
    "bucket_of",
    "build_macro_report",
    "compute_stats",
    "daily_sentiment",
    "effective_session",
    "reliability_label",
    "run_event_study",
    "select_events",
    "sentiment_regime",
    "weekly_timeline",
]
