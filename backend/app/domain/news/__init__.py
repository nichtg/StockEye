"""News helpers that need no I/O: near-duplicate stories, low-value headlines, the month filter."""

from app.domain.news.dedupe import Story, fold_near_duplicates
from app.domain.news.low_value import is_low_value
from app.domain.news.months import InvalidMonthError, month_window
from app.domain.news.similarity import cluster_stories

__all__ = [
    "InvalidMonthError",
    "Story",
    "cluster_stories",
    "fold_near_duplicates",
    "is_low_value",
    "month_window",
]
