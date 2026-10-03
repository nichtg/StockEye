"""Graceful-degradation contract: every analysis response says how trustworthy its inputs are."""

from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel

from app.providers.errors import (
    CircuitOpenError,
    ProviderDataError,
    ProviderError,
    QuotaExhaustedError,
    RateLimitedError,
)

State = Literal["ok", "stale", "partial", "unavailable"]

_SEVERITY: dict[State, int] = {"ok": 0, "stale": 1, "partial": 2, "unavailable": 3}
_MINUTES_CUTOFF = 90  # seconds below which we say "under a minute"
_HOURS_CUTOFF = 90  # minutes below which we count in minutes
_DAYS_CUTOFF_HOURS = 48  # hours below which we count in hours
_DISPLAY_NAMES = {
    "yahoo": "Yahoo Finance",
    "google_news": "Google News",
    "finnhub": "Finnhub",
    "marketaux": "Marketaux",
    "alphavantage": "Alpha Vantage",
}


class DataStatus(BaseModel):
    state: State
    as_of: AwareDatetime | None = None
    reason: str | None = None  # plain English, shown in the UI


def ok(as_of: datetime | None = None, reason: str | None = None) -> DataStatus:
    return DataStatus(state="ok", as_of=as_of, reason=reason)


def combine(statuses: Sequence[DataStatus]) -> DataStatus:
    """Overall state of several inputs.

    The worst state wins, except that a mix of "unavailable" and usable inputs is only
    "partial": the response is still useful, just incomplete. Only when every input is
    unavailable is the whole thing unavailable. ``as_of`` is the oldest known timestamp.
    """
    if not statuses:
        return ok()
    states = [s.state for s in statuses]
    if all(s == "unavailable" for s in states):
        overall: State = "unavailable"
    elif "unavailable" in states:
        overall = "partial"
    else:
        overall = max(states, key=_SEVERITY.__getitem__)
    reasons = [s.reason for s in statuses if s.state != "ok" and s.reason]
    stamps = [s.as_of for s in statuses if s.as_of is not None]
    return DataStatus(
        state=overall,
        as_of=min(stamps) if stamps else None,
        reason=" ".join(reasons) or None,
    )


def provider_label(provider: str) -> str:
    return _DISPLAY_NAMES.get(provider, provider)


def describe_failure(exc: ProviderError) -> str:
    """Short clause naming the provider and what went wrong, for use after a colon."""
    name = provider_label(exc.provider)
    if isinstance(exc, RateLimitedError):
        return f"{name} hit its rate limit"
    if isinstance(exc, QuotaExhaustedError):
        return f"our daily request allowance for {name} is used up"
    if isinstance(exc, CircuitOpenError):
        return f"{name} has been failing repeatedly and is paused for a few minutes"
    if isinstance(exc, ProviderDataError):
        return f"{name} returned data we could not use"
    return f"{name} could not be reached"


def age_phrase(then: datetime, now: datetime) -> str:
    seconds = max(0, int((now - then).total_seconds()))
    if seconds < _MINUTES_CUTOFF:
        return "under a minute"
    minutes = seconds // 60
    if minutes < _HOURS_CUTOFF:
        return f"{minutes} minutes"
    hours = minutes // 60
    if hours < _DAYS_CUTOFF_HOURS:
        return f"{hours} hour{'s' if hours != 1 else ''}"
    return f"{hours // 24} days"


def stale_status(
    label: str, noun: str, then: datetime, now: datetime, exc: ProviderError
) -> DataStatus:
    """Status for "the provider failed, so we show what we saved earlier".

    ``label`` is e.g. "Price data"; ``noun`` is e.g. "prices".
    """
    return DataStatus(
        state="stale",
        as_of=then,
        reason=(
            f"{label} is {age_phrase(then, now)} old: {describe_failure(exc)}. "
            f"Showing the last saved {noun}."
        ),
    )
