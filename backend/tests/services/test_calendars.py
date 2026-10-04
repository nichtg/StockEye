from datetime import UTC, date, datetime

import pytest

from app.services.calendars import (
    exchange_for,
    is_session_open,
    last_completed_session,
    session_calendar,
    session_close,
)


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [("AAPL", "US"), ("D05.SI", "SGX"), ("^STI", "SGX"), ("ES3.SI", "SGX"), ("SPY", "US")],
)
def test_exchange_for_maps_symbols_to_exchanges(symbol: str, expected: str) -> None:
    assert exchange_for(symbol) == expected


def test_is_session_open_during_nyse_hours_returns_true() -> None:
    assert is_session_open("AAPL", datetime(2026, 10, 2, 15, 0, tzinfo=UTC))


def test_is_session_open_on_saturday_returns_false() -> None:
    assert not is_session_open("AAPL", datetime(2026, 10, 3, 15, 0, tzinfo=UTC))


def test_is_session_open_after_sgx_close_returns_false() -> None:
    assert not is_session_open("D05.SI", datetime(2026, 10, 2, 10, 0, tzinfo=UTC))


def test_last_completed_session_mid_session_is_previous_day() -> None:
    now = datetime(2026, 10, 2, 15, 0, tzinfo=UTC)

    assert last_completed_session("AAPL", now) == date(2026, 10, 1)


def test_last_completed_session_after_close_is_same_day() -> None:
    now = datetime(2026, 10, 2, 20, 30, tzinfo=UTC)

    assert last_completed_session("AAPL", now) == date(2026, 10, 2)


def test_last_completed_session_on_weekend_is_friday() -> None:
    assert last_completed_session("D05.SI", datetime(2026, 10, 3, 12, 0, tzinfo=UTC)) == date(
        2026, 10, 2
    )


def test_session_calendar_has_increasing_utc_closes() -> None:
    cal = session_calendar("AAPL", date(2026, 9, 28), date(2026, 10, 2))

    assert len(cal.sessions) == 5
    assert all(c.tzinfo is not None for c in cal.closes_utc)
    assert cal.closes_utc[0] == datetime(2026, 9, 28, 20, 0, tzinfo=UTC)  # 16:00 EDT


def test_session_close_on_holiday_returns_none() -> None:
    assert session_close("AAPL", date(2026, 10, 3)) is None
