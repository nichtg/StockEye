from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from macro_helpers import make_event

from app.domain.macro import (
    bucket_of,
    compute_stats,
    reliability_label,
    sentiment_regime,
    weekly_timeline,
)

D0 = date(2024, 1, 1)


def _day(i: int) -> date:
    return D0 + timedelta(days=i)


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.31, "positive"),
        (0.3, "neutral"),
        (0.0, "neutral"),
        (-0.3, "neutral"),
        (-0.31, "negative"),
        (1.0, "positive"),
        (-1.0, "negative"),
    ],
)
def test_bucket_of_thresholds_are_strict(score, expected):
    assert bucket_of(score) == expected


@pytest.mark.parametrize(
    ("p", "expected"),
    [
        (0.0, "likely_real"),
        (0.049, "likely_real"),
        (0.05, "weak_evidence"),
        (0.199, "weak_evidence"),
        (0.2, "could_be_chance"),
        (0.9, "could_be_chance"),
    ],
)
def test_reliability_label_boundaries(p, expected):
    assert reliability_label(p) == expected


# --- compute_stats ---------------------------------------------------------------------


def _split_events() -> list:
    """10 positive events around +2% and 10 negative ones around -2%, spread of 0.1% steps."""
    pos = [
        make_event(_day(i), 0.6, 0.02 + 0.001 * i, car_0_5=0.03, car_pre_5=0.01) for i in range(10)
    ]
    neg = [
        make_event(_day(20 + i), -0.6, -0.02 + 0.001 * i, car_0_5=-0.03, car_pre_5=-0.01)
        for i in range(10)
    ]
    return pos + neg


def test_compute_stats_welch_difference_matches_hand_calculation():
    stats = compute_stats(_split_events(), exclude_near_earnings=False)

    diff = stats.difference
    assert diff is not None
    assert (diff.n_pos, diff.n_neg) == (10, 10)
    assert diff.mean_diff == pytest.approx(0.04)
    var = float(np.var([0.001 * i for i in range(10)], ddof=1))
    expected_t = 0.04 / np.sqrt(2 * var / 10)
    assert diff.t == pytest.approx(expected_t)
    assert diff.p_value < 1e-10
    assert diff.label == "likely_real"


def test_compute_stats_difference_is_none_when_a_bucket_is_below_min_n():
    events = _split_events()[:-1]  # 10 positive, 9 negative

    stats = compute_stats(events, exclude_near_earnings=False)

    assert stats.difference is None
    assert stats.buckets["negative"].n == 9


def test_compute_stats_difference_none_when_both_groups_constant():
    events = [make_event(_day(i), 0.6, 0.01) for i in range(10)]
    events += [make_event(_day(20 + i), -0.6, 0.01) for i in range(10)]

    assert compute_stats(events, exclude_near_earnings=False).difference is None


def test_compute_stats_spearman_perfect_monotone_relationship():
    events = [make_event(_day(i), -0.9 + 0.15 * i, 0.001 * i) for i in range(12)]

    corr = compute_stats(events, exclude_near_earnings=False).correlation

    assert corr is not None
    assert corr.rho == pytest.approx(1.0)
    assert corr.n == 12
    assert corr.p_value < 0.001
    assert corr.label == "likely_real"


def test_compute_stats_correlation_none_below_min_n_and_never_a_p_value():
    events = [make_event(_day(i), -0.9 + 0.15 * i, 0.001 * i) for i in range(9)]

    stats = compute_stats(events, exclude_near_earnings=False)

    assert stats.correlation is None
    assert stats.n_used == 9


def test_compute_stats_correlation_none_for_constant_inputs():
    constant_car = [make_event(_day(i), 0.1 * i, 0.01) for i in range(12)]
    constant_sent = [make_event(_day(i), 0.5, 0.001 * i) for i in range(12)]

    assert compute_stats(constant_car, exclude_near_earnings=False).correlation is None
    assert compute_stats(constant_sent, exclude_near_earnings=False).correlation is None


def test_compute_stats_respects_custom_min_n():
    events = [make_event(_day(i), -0.9 + 0.3 * i, 0.001 * i) for i in range(6)]

    stats = compute_stats(events, exclude_near_earnings=False, min_n=5)

    assert stats.correlation is not None
    assert stats.correlation.n == 6
    assert stats.min_n == 5


def test_compute_stats_bucket_summaries_skip_missing_car_0_5():
    events = [
        make_event(_day(0), 0.5, 0.01, car_0_5=0.02, car_pre_5=0.0),
        make_event(_day(1), 0.7, 0.03, car_0_5=None, car_pre_5=0.02),
        make_event(_day(2), 0.9, 0.08, car_0_5=0.06, car_pre_5=None),
        make_event(_day(3), 0.0, -0.01),
    ]

    stats = compute_stats(events, exclude_near_earnings=False)

    pos = stats.buckets["positive"]
    assert pos.n == 3
    assert pos.mean_car_0_1 == pytest.approx(0.04)
    assert pos.median_car_0_1 == pytest.approx(0.03)
    assert pos.n_car_0_5 == 2
    assert pos.mean_car_0_5 == pytest.approx(0.04)
    assert pos.median_car_0_5 == pytest.approx(0.04)
    assert pos.mean_car_pre_5 == pytest.approx(0.01)
    neutral = stats.buckets["neutral"]
    assert neutral.n == 1
    assert neutral.mean_car_0_5 is None
    assert neutral.mean_car_pre_5 is None
    empty = stats.buckets["negative"]
    assert (empty.n, empty.mean_car_0_1, empty.median_car_0_1) == (0, None, None)


def test_compute_stats_excludes_unusable_events():
    events = [
        make_event(_day(0), 0.6, 0.01),
        make_event(_day(1), 0.6, None),  # no forward window
        make_event(_day(2), 0.6, None, ok=False),  # insufficient estimation
    ]

    assert compute_stats(events, exclude_near_earnings=False).n_used == 1


def test_compute_stats_earnings_exclusion_removes_confounded_events():
    events = _split_events()
    events += [make_event(_day(40 + i), 0.8, 0.5, near_earnings=True) for i in range(10)]

    with_earn = compute_stats(events, exclude_near_earnings=False)
    without = compute_stats(events, exclude_near_earnings=True)

    assert with_earn.n_used == 30
    assert without.n_used == 20
    assert without.exclude_near_earnings is True
    assert without.buckets["positive"].mean_car_0_1 == pytest.approx(0.0245)
    assert with_earn.buckets["positive"].mean_car_0_1 is not None
    assert with_earn.buckets["positive"].mean_car_0_1 > 0.2


# --- regime and timeline -----------------------------------------------------------------


def _weekly_frame(means: list[float]) -> pd.DataFrame:
    """One single-article row on the Wednesday of consecutive weeks starting 2024-01-03."""
    idx = pd.DatetimeIndex(
        [pd.Timestamp("2024-01-03") + pd.Timedelta(weeks=i) for i in range(len(means))]
    )
    return pd.DataFrame(
        {"mean_score": means, "article_count": 1, "max_abs_score": np.abs(means)}, index=idx
    )


def test_sentiment_regime_z_score_matches_hand_calculation():
    means = [0.1 if i % 2 == 0 else -0.1 for i in range(19)] + [0.9]
    frame = _weekly_frame(means)
    as_of = (frame.index[-1] + pd.Timedelta(days=2)).date()  # the Friday of the last week

    regime = sentiment_regime(frame, as_of)

    assert regime is not None
    # Window (as_of - 30d, as_of] holds the last four Wednesdays: 0.1, -0.1, 0.1, 0.9.
    assert regime.recent_mean == pytest.approx(0.25)
    assert regime.recent_articles == 4
    baseline = float(np.mean(means))
    assert regime.baseline_mean == pytest.approx(baseline)
    assert regime.z == pytest.approx((0.25 - baseline) / float(np.std(means, ddof=1)))
    assert regime.label == "typical"  # z is about 1.0 - 0.0x; check bounds below
    assert abs(regime.z) < 1


def test_sentiment_regime_labels_more_positive_and_more_negative():
    base = [0.1 if i % 2 == 0 else -0.1 for i in range(16)]
    up = _weekly_frame([*base, 0.9, 0.9, 0.9, 0.9])
    down = _weekly_frame([*base, -0.9, -0.9, -0.9, -0.9])

    r_up = sentiment_regime(up, (up.index[-1] + pd.Timedelta(days=2)).date())
    r_down = sentiment_regime(down, (down.index[-1] + pd.Timedelta(days=2)).date())

    assert r_up is not None
    assert r_down is not None
    assert r_up.label == "more_positive_than_usual"
    assert r_down.label == "more_negative_than_usual"
    assert r_up.z >= 1
    assert r_down.z <= -1


def test_sentiment_regime_none_with_fewer_than_twelve_weeks():
    frame = _weekly_frame([0.1, -0.1, 0.2, 0.0, 0.3, -0.2, 0.1, 0.0, 0.2, -0.1, 0.4])
    assert sentiment_regime(frame, (frame.index[-1]).date()) is None


def test_sentiment_regime_none_without_recent_news():
    frame = _weekly_frame([0.1 if i % 2 == 0 else -0.1 for i in range(20)])
    far_future = (frame.index[-1] + pd.Timedelta(days=60)).date()
    assert sentiment_regime(frame, far_future) is None


def test_sentiment_regime_none_for_empty_or_pre_history_as_of():
    frame = _weekly_frame([0.1 if i % 2 == 0 else -0.1 for i in range(20)])
    assert sentiment_regime(frame, date(2020, 1, 1)) is None
    assert sentiment_regime(frame.iloc[0:0], date(2024, 6, 1)) is None


def test_sentiment_regime_none_when_weekly_sentiment_is_constant():
    frame = _weekly_frame([0.2] * 20)
    assert sentiment_regime(frame, (frame.index[-1]).date()) is None


def test_sentiment_regime_ignores_news_after_as_of():
    means = [0.1 if i % 2 == 0 else -0.1 for i in range(20)]
    frame = _weekly_frame(means)
    as_of = frame.index[15].date()
    future_junk = _weekly_frame([0.1 if i % 2 == 0 else -0.1 for i in range(16)] + [0.9] * 10)

    assert sentiment_regime(frame, as_of) == sentiment_regime(future_junk, as_of)


def test_sentiment_regime_weights_by_article_count():
    means = [0.1 if i % 2 == 0 else -0.1 for i in range(16)] + [0.0, 0.0, 0.0, 0.0]
    frame = _weekly_frame(means)
    frame.loc[frame.index[-1], ["mean_score", "article_count"]] = [0.8, 9]
    as_of = (frame.index[-1] + pd.Timedelta(days=2)).date()

    regime = sentiment_regime(frame, as_of)

    assert regime is not None
    assert regime.recent_articles == 12
    assert regime.recent_mean == pytest.approx(0.8 * 9 / 12)


def test_weekly_timeline_weights_by_article_count_and_labels_week_end_friday():
    idx = pd.DatetimeIndex(["2024-01-01", "2024-01-02", "2024-01-10"])
    frame = pd.DataFrame(
        {"mean_score": [0.2, 0.8, -0.5], "article_count": [1, 3, 2], "max_abs_score": 0.8},
        index=idx,
    )

    points = weekly_timeline(frame)

    assert [p.week_end for p in points] == [date(2024, 1, 5), date(2024, 1, 12)]
    assert points[0].mean_score == pytest.approx((0.2 + 2.4) / 4)
    assert points[0].article_count == 4
    assert points[1].mean_score == pytest.approx(-0.5)


def test_weekly_timeline_omits_empty_weeks_and_handles_empty_frame():
    frame = _weekly_frame([0.1, 0.2])
    frame.index = pd.DatetimeIndex(["2024-01-03", "2024-01-24"])  # two weeks of silence between

    assert [p.week_end for p in weekly_timeline(frame)] == [date(2024, 1, 5), date(2024, 1, 26)]
    assert weekly_timeline(frame.iloc[0:0]) == []


def test_compute_stats_single_observation_groups_give_no_welch_test():
    events = [make_event(_day(0), 0.6, 0.02), make_event(_day(1), -0.6, -0.02)]

    stats = compute_stats(events, exclude_near_earnings=False, min_n=1)

    assert stats.difference is None  # variance of one observation is undefined
    assert stats.correlation is not None
