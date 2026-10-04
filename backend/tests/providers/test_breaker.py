from datetime import UTC, datetime, timedelta

from app.providers.breaker import CircuitBreaker


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


def _tripped(clock: FakeClock) -> CircuitBreaker:
    breaker = CircuitBreaker(threshold=5, cooldown=timedelta(minutes=2), clock=clock)
    for _ in range(5):
        breaker.record_failure()
    return breaker


def test_breaker_below_threshold_stays_closed() -> None:
    breaker = CircuitBreaker(clock=FakeClock())

    for _ in range(4):
        breaker.record_failure()

    assert breaker.state == "closed"
    assert breaker.allow()


def test_breaker_success_resets_consecutive_failures() -> None:
    breaker = CircuitBreaker(clock=FakeClock())

    for _ in range(4):
        breaker.record_failure()
    breaker.record_success()
    for _ in range(4):
        breaker.record_failure()

    assert breaker.state == "closed"


def test_breaker_opens_after_threshold_and_refuses_calls() -> None:
    breaker = _tripped(FakeClock())

    assert breaker.state == "open"
    assert not breaker.allow()


def test_breaker_half_opens_after_cooldown_and_allows_single_trial() -> None:
    clock = FakeClock()
    breaker = _tripped(clock)

    clock.advance(minutes=2)

    assert breaker.state == "half_open"
    assert breaker.allow()
    assert not breaker.allow()  # only one trial at a time


def test_breaker_trial_success_closes() -> None:
    clock = FakeClock()
    breaker = _tripped(clock)
    clock.advance(minutes=3)
    assert breaker.allow()

    breaker.record_success()

    assert breaker.state == "closed"
    assert breaker.allow()


def test_breaker_trial_failure_reopens_for_a_full_cooldown() -> None:
    clock = FakeClock()
    breaker = _tripped(clock)
    clock.advance(minutes=3)
    assert breaker.allow()

    breaker.record_failure()

    states = [breaker.state]
    clock.advance(minutes=1)
    states.append(breaker.state)
    clock.advance(minutes=1)
    states.append(breaker.state)
    assert states == ["open", "open", "half_open"]


def test_breaker_released_trial_slot_can_be_taken_again() -> None:
    clock = FakeClock()
    breaker = _tripped(clock)
    clock.advance(minutes=3)
    assert breaker.allow()

    breaker.release_trial()

    assert breaker.allow()
