"""In-memory circuit breaker, one per provider.

closed -> open after ``threshold`` consecutive failures -> half_open once the cooldown elapses.
In half_open exactly one trial call is let through; its outcome closes or re-opens the breaker.
State is per process by design: a restart resets it, which is the safe direction.
"""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Literal

from app.clock import utc_now

BreakerState = Literal["closed", "open", "half_open"]


class CircuitBreaker:
    def __init__(
        self,
        threshold: int = 5,
        cooldown: timedelta = timedelta(minutes=2),
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._threshold = threshold
        self._cooldown = cooldown
        self._clock = clock
        self._failures = 0
        self._opened_at: datetime | None = None
        self._trial_in_flight = False

    @property
    def state(self) -> BreakerState:
        if self._opened_at is None:
            return "closed"
        if self._clock() - self._opened_at >= self._cooldown:
            return "half_open"
        return "open"

    def allow(self) -> bool:
        """True if a call may proceed. In half_open only the first caller gets the trial."""
        state = self.state
        if state == "closed":
            return True
        if state == "open":
            return False
        if self._trial_in_flight:
            return False
        self._trial_in_flight = True
        return True

    def release_trial(self) -> None:
        """Give back a half_open trial slot when the call was never actually made."""
        self._trial_in_flight = False

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None
        self._trial_in_flight = False

    def record_failure(self) -> None:
        self._trial_in_flight = False
        if self._opened_at is not None:
            # A failed half_open trial (or a straggler) restarts the cooldown.
            self._opened_at = self._clock()
            return
        self._failures += 1
        if self._failures >= self._threshold:
            self._opened_at = self._clock()
