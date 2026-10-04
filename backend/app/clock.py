"""The one default clock; services take a ``Callable[[], datetime]`` so tests can freeze time."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)
