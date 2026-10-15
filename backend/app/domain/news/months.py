"""The News tab's month filter: parse "YYYY-MM" and clip it to the window (pure)."""

import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

_MONTH = re.compile(r"^([0-9]{4})-(0[1-9]|1[0-2])$")  # ASCII digits only


class InvalidMonthError(ValueError):
    """The month is malformed or lies wholly outside the window."""


def month_window(
    month: str, tz: ZoneInfo, now: datetime, since: datetime
) -> tuple[datetime, datetime]:
    """UTC ``[start, end)`` of the exchange-local calendar ``month``, clipped to ``since``.

    ``since`` is the (inclusive) window start and ``now`` its end. Raises
    ``InvalidMonthError`` for anything but ``YYYY-MM``, a year outside datetime's range, or a
    month that ends at or before ``since`` or starts after ``now`` (it could hold nothing).
    """
    match = _MONTH.fullmatch(month)
    if match is None:
        raise InvalidMonthError(month)
    year, number = int(match[1]), int(match[2])
    try:
        start = datetime(year, number, 1, tzinfo=tz).astimezone(UTC)
        end = datetime(year + number // 12, number % 12 + 1, 1, tzinfo=tz).astimezone(UTC)
    except (ValueError, OverflowError) as exc:  # year 0000 or 9999
        raise InvalidMonthError(month) from exc
    if end <= since or start > now:
        raise InvalidMonthError(month)
    return max(start, since), end
