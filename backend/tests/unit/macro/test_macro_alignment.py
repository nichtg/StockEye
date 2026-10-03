from datetime import UTC, date, datetime, time, timedelta

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st
from macro_helpers import NY, SGT, make_calendar

from app.domain.macro import (
    ScoredArticle,
    SessionCalendar,
    daily_sentiment,
    effective_session,
)

# 2024-03-04 is a Monday. NY close is 16:00 local (EST, UTC-5 until 10 March).
CAL = make_calendar(date(2024, 3, 4), 30)


def _article(ts: datetime, score: float = 0.5, title: str = "t") -> ScoredArticle:
    return ScoredArticle(published_at=ts, score=score, title=title, url="u", source="s")


def test_effective_session_one_second_before_close_maps_to_same_session():
    ts = datetime(2024, 3, 5, 15, 59, 59, tzinfo=NY)
    assert effective_session(ts, CAL) == date(2024, 3, 5)


def test_effective_session_exactly_at_close_maps_to_next_session():
    ts = datetime(2024, 3, 5, 16, 0, 0, tzinfo=NY)
    assert effective_session(ts, CAL) == date(2024, 3, 6)


def test_effective_session_one_second_after_close_maps_to_next_session():
    ts = datetime(2024, 3, 5, 16, 0, 1, tzinfo=NY)
    assert effective_session(ts, CAL) == date(2024, 3, 6)


def test_effective_session_saturday_maps_to_monday():
    ts = datetime(2024, 3, 9, 12, 0, tzinfo=NY)
    assert effective_session(ts, CAL) == date(2024, 3, 11)


def test_effective_session_friday_after_close_maps_to_monday():
    ts = datetime(2024, 3, 8, 18, 0, tzinfo=NY)
    assert effective_session(ts, CAL) == date(2024, 3, 11)


def test_effective_session_before_first_session_maps_to_first():
    ts = datetime(2020, 1, 1, tzinfo=UTC)
    assert effective_session(ts, CAL) == date(2024, 3, 4)


def test_effective_session_after_last_close_returns_none():
    ts = CAL.closes_utc[-1] + timedelta(seconds=1)
    assert effective_session(ts, CAL) is None


def test_effective_session_naive_datetime_raises():
    with pytest.raises(ValueError, match="timezone-aware"):
        effective_session(datetime(2024, 3, 5, 10, 0), CAL)  # noqa: DTZ001


def test_effective_session_singapore_morning_after_us_close_maps_to_next_us_session():
    # 09:00 SGT on Wed 6 Mar is 20:00 EST on Tue 5 Mar: the US close has passed -> Wed.
    ts = datetime(2024, 3, 6, 9, 0, tzinfo=SGT)
    assert effective_session(ts, CAL) == date(2024, 3, 6)


def test_effective_session_singapore_early_morning_maps_to_open_us_session():
    # 02:00 SGT on Wed 6 Mar is 13:00 EST on Tue 5 Mar: the US session is open -> Tue.
    ts = datetime(2024, 3, 6, 2, 0, tzinfo=SGT)
    assert effective_session(ts, CAL) == date(2024, 3, 5)


def test_effective_session_sgx_calendar_close_boundary():
    sgx = make_calendar(date(2024, 3, 4), 10, tz=SGT, close=time(17, 0))
    before = datetime(2024, 3, 5, 16, 59, 59, tzinfo=SGT)
    at = datetime(2024, 3, 5, 17, 0, 0, tzinfo=SGT)
    assert effective_session(before, sgx) == date(2024, 3, 5)
    assert effective_session(at, sgx) == date(2024, 3, 6)


def test_effective_session_across_dst_change_uses_utc_close():
    # DST began 10 Mar 2024; the close moves from 21:00 UTC to 20:00 UTC.
    cal = make_calendar(date(2024, 3, 7), 6)
    assert cal.closes_utc[0].hour == 21
    assert cal.closes_utc[-1].hour == 20
    ts = datetime(2024, 3, 12, 20, 0, 1, tzinfo=UTC)  # just after the Tuesday close in EDT
    assert effective_session(ts, cal) == date(2024, 3, 13)


@given(offset_s=st.integers(min_value=-5 * 86400, max_value=40 * 86400))
def test_effective_session_property_close_after_and_previous_close_not_after(offset_s):
    ts = CAL.closes_utc[0] + timedelta(seconds=offset_s)
    session = effective_session(ts, CAL)
    if session is None:
        assert ts >= CAL.closes_utc[-1]
        return
    i = CAL.sessions.index(session)
    assert CAL.closes_utc[i] > ts
    if i > 0:
        assert CAL.closes_utc[i - 1] <= ts


def test_calendar_rejects_length_mismatch():
    with pytest.raises(ValueError, match="equal length"):
        SessionCalendar(sessions=(date(2024, 3, 4),), closes_utc=())


def test_calendar_rejects_naive_closes():
    with pytest.raises(ValueError, match="timezone-aware"):
        SessionCalendar(sessions=(date(2024, 3, 4),), closes_utc=(datetime(2024, 3, 4, 21),))  # noqa: DTZ001


def test_calendar_rejects_non_increasing_sessions():
    c = datetime(2024, 3, 4, 21, tzinfo=UTC)
    with pytest.raises(ValueError, match="sessions must be strictly increasing"):
        SessionCalendar(
            sessions=(date(2024, 3, 5), date(2024, 3, 4)),
            closes_utc=(c, c + timedelta(days=1)),
        )


def test_calendar_rejects_non_increasing_closes():
    c = datetime(2024, 3, 4, 21, tzinfo=UTC)
    with pytest.raises(ValueError, match="closes_utc must be strictly increasing"):
        SessionCalendar(sessions=(date(2024, 3, 4), date(2024, 3, 5)), closes_utc=(c, c))


def test_daily_sentiment_aggregates_per_session_and_omits_silent_days():
    arts = [
        _article(datetime(2024, 3, 5, 10, 0, tzinfo=NY), 0.8, "a"),
        _article(datetime(2024, 3, 5, 11, 0, tzinfo=NY), -0.4, "b"),
        _article(datetime(2024, 3, 5, 17, 0, tzinfo=NY), 0.2, "c"),  # after close -> Wed
        _article(datetime(2024, 3, 9, 9, 0, tzinfo=NY), -0.6, "d"),  # Sat -> Mon 11th
    ]
    frame, by_session = daily_sentiment(arts, CAL)

    assert list(frame.index) == [
        pd.Timestamp(d) for d in ("2024-03-05", "2024-03-06", "2024-03-11")
    ]
    tue = frame.loc["2024-03-05"]
    assert tue["mean_score"] == pytest.approx(0.2)
    assert tue["article_count"] == 2
    assert tue["max_abs_score"] == pytest.approx(0.8)
    assert frame.loc["2024-03-06", "mean_score"] == pytest.approx(0.2)
    assert date(2024, 3, 7) not in by_session  # silent days absent, not zero
    assert [a.title for a in by_session[date(2024, 3, 5)]] == ["a", "b"]
    assert [a.title for a in by_session[date(2024, 3, 11)]] == ["d"]


def test_daily_sentiment_drops_articles_after_last_session_and_handles_empty():
    late = _article(CAL.closes_utc[-1] + timedelta(hours=1))
    frame, by_session = daily_sentiment([late], CAL)
    assert frame.empty
    assert by_session == {}
    assert list(frame.columns) == ["mean_score", "article_count", "max_abs_score"]
