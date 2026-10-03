from datetime import UTC, datetime, timedelta

from app.providers.errors import (
    CircuitOpenError,
    ProviderDataError,
    QuotaExhaustedError,
    RateLimitedError,
    TransientProviderError,
)
from app.services.status import DataStatus, age_phrase, combine, describe_failure, stale_status

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def _status(state: str, reason: str | None = None, as_of: datetime | None = None) -> DataStatus:
    return DataStatus.model_validate({"state": state, "as_of": as_of, "reason": reason})


def test_combine_worst_state_wins() -> None:
    result = combine([_status("ok"), _status("stale", "old"), _status("partial", "some")])

    assert result.state == "partial"
    assert result.reason == "old some"


def test_combine_mix_of_unavailable_and_usable_is_partial() -> None:
    assert combine([_status("ok"), _status("unavailable", "gone")]).state == "partial"


def test_combine_all_unavailable_is_unavailable() -> None:
    assert combine([_status("unavailable"), _status("unavailable")]).state == "unavailable"


def test_combine_as_of_is_the_oldest_timestamp() -> None:
    older = NOW - timedelta(hours=3)

    result = combine([_status("ok", as_of=NOW), _status("stale", as_of=older)])

    assert result.as_of == older


def test_combine_empty_is_ok() -> None:
    assert combine([]).state == "ok"


def test_stale_status_reason_names_provider_and_age() -> None:
    status = stale_status(
        "Price data", "prices", NOW - timedelta(hours=3), NOW, RateLimitedError("yahoo")
    )

    assert status.state == "stale"
    assert status.reason == (
        "Price data is 3 hours old: Yahoo Finance hit its rate limit. "
        "Showing the last saved prices."
    )


def test_describe_failure_covers_each_error_kind() -> None:
    assert "paused" in describe_failure(CircuitOpenError("yahoo", "open"))
    assert "allowance" in describe_failure(QuotaExhaustedError("yahoo", "x"))
    assert "unusable" in describe_failure(ProviderDataError("yahoo", "x")) or "could not use" in (
        describe_failure(ProviderDataError("yahoo", "x"))
    )
    assert "could not be reached" in describe_failure(TransientProviderError("google_news", "x"))


def test_age_phrase_scales_units() -> None:
    assert age_phrase(NOW - timedelta(seconds=20), NOW) == "under a minute"
    assert age_phrase(NOW - timedelta(minutes=12), NOW) == "12 minutes"
    assert age_phrase(NOW - timedelta(hours=1), NOW) == "60 minutes"
    assert age_phrase(NOW - timedelta(hours=1, minutes=40), NOW) == "1 hour"
    assert age_phrase(NOW - timedelta(days=3), NOW) == "3 days"


def test_describe_failure_names_the_window_of_a_quota_block() -> None:
    minute = QuotaExhaustedError("finnhub", "blocked", window="minute")
    day = QuotaExhaustedError("finnhub", "blocked", window="day")

    assert "per-minute limit" in describe_failure(minute)
    assert "daily" not in describe_failure(minute)
    assert "daily request allowance" in describe_failure(day)
