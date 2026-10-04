from datetime import UTC, datetime

import pytest

from app.providers.models import Quote


def _quote(price: float, previous_close: float) -> Quote:
    return Quote(
        symbol="AAPL",
        name="Apple Inc.",
        exchange="US",
        currency="USD",
        price=price,
        previous_close=previous_close,
        as_of=datetime(2026, 10, 3, tzinfo=UTC),
    )


def test_change_pct_is_the_move_versus_the_previous_close_in_percent() -> None:
    assert _quote(110.0, 100.0).change_pct == pytest.approx(10.0)
    assert _quote(95.0, 100.0).change_pct == pytest.approx(-5.0)


def test_change_pct_without_a_previous_close_is_none() -> None:
    assert _quote(110.0, 0.0).change_pct is None
