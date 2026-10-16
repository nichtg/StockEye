"""Whole-calendar-month arithmetic (pure)."""

import calendar
from datetime import datetime


def months_before(moment: datetime, months: int) -> datetime:
    """``moment`` moved back by whole calendar months, the day clamped to the month's length.

    (31 Mar minus one month is 28 Feb; time of day and timezone are kept.)
    """
    index = moment.year * 12 + moment.month - 1 - months
    year, month = divmod(index, 12)
    month += 1
    return moment.replace(
        year=year, month=month, day=min(moment.day, calendar.monthrange(year, month)[1])
    )
