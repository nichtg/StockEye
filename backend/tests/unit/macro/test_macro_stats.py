from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from macro_helpers import make_event
from scipy import stats as stats_lib

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


AS_OF = date(2024, 12, 31)


def _block_frame(means: list[float], counts: list[int] | None = None) -> pd.DataFrame:
    """One row per 30-day block, oldest first; the last row is inside the recent window."""
    n = len(means)
    idx = pd.DatetimeIndex(
        [pd.Timestamp(AS_OF) - pd.Timedelta(days=30 * (n - 1 - i) + 10) for i in range(n)]
    )
    cnt = counts or [1] * n
    return pd.DataFrame(
        {"mean_score": means, "article_count": cnt, "max_abs_score": np.abs(means)}, index=idx
    )


def test_sentiment_regime_z_score_matches_hand_calculation():
    baseline_blocks = [0.1, -0.1, 0.2, 0.0, -0.2, 0.1, 0.0, 0.1, -0.1]
    frame = _block_frame([*baseline_blocks, 0.25])

    regime = sentiment_regime(frame, AS_OF)

    assert regime is not None
    assert regime.recent_mean == pytest.approx(0.25)
    assert regime.recent_articles == 1
    assert regime.baseline_mean == pytest.approx(float(np.mean(baseline_blocks)))
    expected = (0.25 - np.mean(baseline_blocks)) / np.std(baseline_blocks, ddof=1)
    assert regime.z == pytest.approx(float(expected))
    assert regime.label == "more_positive_than_usual"


def test_sentiment_regime_recent_window_is_thirty_days_and_blocks_do_not_overlap():
    base = [0.1 if i % 2 == 0 else -0.1 for i in range(8)]
    frame = _block_frame([*base, 0.9])
    # Two extra rows inside the recent window (age 0 and 29 days) join its weighted mean;
    # a row aged exactly 30 days falls into the first baseline block instead.
    extra = pd.DataFrame(
        {"mean_score": [0.5, 0.5, 0.3], "article_count": [1, 1, 1], "max_abs_score": 0.5},
        index=pd.DatetimeIndex([pd.Timestamp(AS_OF) - pd.Timedelta(days=d) for d in (0, 29, 30)]),
    )

    regime = sentiment_regime(pd.concat([frame, extra]).sort_index(), AS_OF)

    assert regime is not None
    assert regime.recent_articles == 3
    assert regime.recent_mean == pytest.approx((0.9 + 0.5 + 0.5) / 3)


def test_sentiment_regime_labels_more_positive_and_more_negative():
    base = [0.1 if i % 2 == 0 else -0.1 for i in range(10)]
    r_up = sentiment_regime(_block_frame([*base, 0.9]), AS_OF)
    r_down = sentiment_regime(_block_frame([*base, -0.9]), AS_OF)

    assert r_up is not None
    assert r_down is not None
    assert r_up.label == "more_positive_than_usual"
    assert r_down.label == "more_negative_than_usual"
    assert r_up.z >= 1
    assert r_down.z <= -1


def test_sentiment_regime_typical_when_recent_is_near_baseline():
    base = [0.1 if i % 2 == 0 else -0.1 for i in range(10)]
    regime = sentiment_regime(_block_frame([*base, 0.0]), AS_OF)

    assert regime is not None
    assert regime.label == "typical"
    assert abs(regime.z) < 1


def test_sentiment_regime_none_with_fewer_than_eight_baseline_blocks():
    seven = [0.1 if i % 2 == 0 else -0.1 for i in range(7)]
    eight = [*seven, 0.1]

    assert sentiment_regime(_block_frame([*seven, 0.3]), AS_OF) is None
    assert sentiment_regime(_block_frame([*eight, 0.3]), AS_OF) is not None


def test_sentiment_regime_skips_empty_blocks_but_still_needs_eight_with_news():
    base = [0.1 if i % 2 == 0 else -0.1 for i in range(9)]
    frame = _block_frame([*base, 0.3])
    gappy = frame.drop(frame.index[2])  # an empty block is skipped, 8 remain

    assert sentiment_regime(gappy, AS_OF) is not None
    assert sentiment_regime(gappy.drop(gappy.index[2]), AS_OF) is None


def test_sentiment_regime_none_without_recent_news():
    frame = _block_frame([0.1 if i % 2 == 0 else -0.1 for i in range(11)])
    assert sentiment_regime(frame.iloc[:-1], AS_OF) is None


def test_sentiment_regime_none_for_empty_or_pre_history_as_of():
    frame = _block_frame([0.1 if i % 2 == 0 else -0.1 for i in range(11)])
    assert sentiment_regime(frame, date(2020, 1, 1)) is None
    assert sentiment_regime(frame.iloc[0:0], AS_OF) is None


def test_sentiment_regime_none_when_block_sentiment_is_constant():
    assert sentiment_regime(_block_frame([0.2] * 11), AS_OF) is None


def test_sentiment_regime_ignores_news_after_as_of():
    base = [0.1 if i % 2 == 0 else -0.1 for i in range(10)]
    frame = _block_frame([*base, 0.2])
    future = pd.DataFrame(
        {"mean_score": [0.9, 0.9], "article_count": [5, 5], "max_abs_score": 0.9},
        index=pd.DatetimeIndex([pd.Timestamp(AS_OF) + pd.Timedelta(days=d) for d in (1, 40)]),
    )

    assert sentiment_regime(frame, AS_OF) == sentiment_regime(pd.concat([frame, future]), AS_OF)


def test_sentiment_regime_weights_by_article_count():
    base = [0.1 if i % 2 == 0 else -0.1 for i in range(9)]
    frame = _block_frame([*base, 0.0], [1] * 9 + [1])
    frame.loc[frame.index[-1], ["mean_score", "article_count"]] = [0.8, 9]
    extra = pd.DataFrame(
        {"mean_score": [0.0], "article_count": [3], "max_abs_score": 0.0},
        index=pd.DatetimeIndex([pd.Timestamp(AS_OF)]),
    )

    regime = sentiment_regime(pd.concat([frame, extra]), AS_OF)

    assert regime is not None
    assert regime.recent_articles == 12
    assert regime.recent_mean == pytest.approx(0.8 * 9 / 12)


def test_sentiment_regime_null_simulation_flags_a_plausible_share_as_unusual():
    # With i.i.d. news the label should fire about a third of the time (|z| >= 1). A recent
    # 30-day mean compared with weekly spread would almost never fire.
    rng = np.random.default_rng(11)
    days = pd.date_range(end=pd.Timestamp(AS_OF), periods=720, freq="D")
    labels = []
    for _ in range(300):
        keep = rng.random(len(days)) < 0.5
        idx = days[keep]
        frame = pd.DataFrame(
            {
                "mean_score": rng.normal(0.0, 0.4, len(idx)),
                "article_count": rng.integers(1, 6, len(idx)),
                "max_abs_score": 0.4,
            },
            index=idx,
        )
        regime = sentiment_regime(frame, AS_OF)
        assert regime is not None
        labels.append(regime.label != "typical")

    share = float(np.mean(labels))
    assert 0.2 <= share <= 0.45


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


def test_compute_stats_bucket_gets_its_own_one_sample_t_test_against_zero():
    cars = [0.01, 0.02, 0.015, 0.03, -0.005, 0.02, 0.01, 0.025, 0.012, 0.018]
    events = [make_event(_day(i), 0.6, c) for i, c in enumerate(cars)]

    bucket = compute_stats(events, exclude_near_earnings=False).buckets["positive"]

    expected = stats_lib.ttest_1samp(cars, 0.0)
    assert bucket.t == pytest.approx(float(expected.statistic))
    assert bucket.p_value == pytest.approx(float(expected.pvalue))
    assert bucket.label == "likely_real"


def test_compute_stats_bucket_test_is_none_below_min_n_or_without_spread():
    thin = [make_event(_day(i), 0.6, 0.01 * i) for i in range(9)]
    flat = [make_event(_day(i), -0.6, 0.01) for i in range(12)]

    stats = compute_stats([*thin, *flat], exclude_near_earnings=False)

    assert stats.buckets["positive"].p_value is None  # 9 < min_n
    assert stats.buckets["positive"].label is None
    assert stats.buckets["negative"].p_value is None  # constant: t undefined
    assert stats.buckets["neutral"].t is None
