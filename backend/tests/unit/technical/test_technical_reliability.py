# ruff: noqa: RUF005
"""Reliability tests on hand-computed forward returns."""

import numpy as np
import pandas as pd
import pytest
from technical_refs import frame, ref_wilson, trend_is

from app.domain.technical import (
    PatternHit,
    PatternKey,
    pattern_reliability,
    wilson_interval,
)
from app.domain.technical.candlesticks import PATTERNS, trend_context

K = PatternKey


def _hit(key: PatternKey, index: int, df: pd.DataFrame) -> PatternHit:
    return PatternHit(key, PATTERNS[key].bias, index, df.index[index].to_pydatetime())


def _ctx(df: pd.DataFrame, value: str) -> pd.Series:
    """A trend-context series that is the same everywhere (the hand fixtures are too short
    for a real 10-bar SMA trend)."""
    return pd.Series(value, index=df.index, dtype=object)


def _daily(closes: list[float]) -> pd.DataFrame:
    return frame([(c, c + 1.0, c - 1.0, c) for c in closes])


def _fixture() -> pd.DataFrame:
    # open is 100 everywhere, so with horizon 3: ret[t] = close[t+3] / 100 - 1
    closes = [100, 101, 102, 99, 98, 103, 104, 97, 105, 106, 95, 107]
    return frame([(100.0, 110.0, 90.0, float(c)) for c in closes])


# Forward returns by hand (t = 0..8; t = 9..11 have no t+3 bar):
#   t0 -.01  t1 -.02  t2 +.03  t3 +.04  t4 -.03  t5 +.05  t6 +.06  t7 -.05  t8 +.07
# 5 of 9 are positive -> base_up_rate = 5/9.
BASE_UP = 5 / 9


def test_wilson_interval_known_value_nine_of_twelve() -> None:
    low, high = wilson_interval(9, 12)

    assert low == pytest.approx(0.468, abs=5e-4)
    assert high == pytest.approx(0.911, abs=5e-4)


@pytest.mark.parametrize(("s", "n"), [(1, 2), (0, 10), (10, 10), (3, 7), (50, 80)])
def test_wilson_interval_matches_closed_form_reference(s: int, n: int) -> None:
    low, high = wilson_interval(s, n)
    ref_low, ref_high = ref_wilson(s, n)

    assert low == pytest.approx(max(0.0, ref_low))
    assert high == pytest.approx(min(1.0, ref_high))


def test_wilson_interval_without_samples_is_uninformative() -> None:
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_pattern_reliability_bullish_non_overlapping_walk_counts_hand_values() -> None:
    df = _fixture()
    # Walk (horizon 3): t0 counted; t1, t2 within 3 of t0 -> skipped; t3 counted (3 - 0 = 3);
    # t4, t5 skipped; t9 and t11 have no t+3 bar -> dropped.
    hits = [_hit(K.HAMMER, t, df) for t in (0, 1, 2, 3, 4, 5, 9, 11)]

    stats = pattern_reliability(df, hits, horizon=3, min_samples=2, trend=_ctx(df, "down"))[
        K.HAMMER
    ]

    assert stats.n == 2  # returns -0.01 and +0.04
    assert stats.up_count == 1
    assert stats.success_count == 1
    assert stats.hit_rate == pytest.approx(0.5)
    assert stats.mean_return == pytest.approx(0.015)
    assert stats.median_return == pytest.approx(0.015)
    assert stats.base_up_rate == pytest.approx(BASE_UP)
    assert stats.base_rate == pytest.approx(BASE_UP)
    assert stats.edge == pytest.approx(0.5 - BASE_UP)
    assert (stats.wilson_low, stats.wilson_high) == pytest.approx(wilson_interval(1, 2))
    assert stats.sufficient is True


def test_pattern_reliability_bearish_success_means_negative_return() -> None:
    df = _fixture()
    # t0 -.01 (counted), t3 +.04 (3 - 0 = 3, counted), t6 +.06 (counted), t7 skipped.
    hits = [_hit(K.EVENING_STAR, t, df) for t in (0, 3, 6, 7)]

    stats = pattern_reliability(df, hits, horizon=3, trend=_ctx(df, "up"))[K.EVENING_STAR]

    assert stats.n == 3
    assert stats.up_count == 2
    assert stats.success_count == 1
    assert stats.hit_rate == pytest.approx(1 / 3)
    assert stats.mean_return == pytest.approx(0.03)
    assert stats.median_return == pytest.approx(0.04)
    assert stats.base_down_rate == pytest.approx(4 / 9)  # t0, t1, t4, t7 are negative
    assert stats.base_rate == pytest.approx(4 / 9)
    assert stats.edge == pytest.approx(1 / 3 - 4 / 9)
    assert stats.sufficient is False  # 3 < default min_samples 15


def test_pattern_reliability_neutral_has_no_success_metrics() -> None:
    df = _fixture()
    hits = [_hit(K.DOJI, 4, df), _hit(K.DOJI, 8, df)]  # t4 -.03, t8 +.07 (8 - 4 >= 3)

    stats = pattern_reliability(df, hits, horizon=3, min_samples=2)[K.DOJI]

    assert stats.n == 2
    assert stats.up_count == 1
    assert stats.success_count is None
    assert stats.hit_rate is None
    assert stats.wilson_low is None
    assert stats.wilson_high is None
    assert stats.base_rate is None
    assert stats.edge is None
    assert stats.mean_return == pytest.approx(0.02)
    assert stats.median_return == pytest.approx(0.02)
    assert stats.base_up_rate == pytest.approx(BASE_UP)
    assert stats.sufficient is True


def test_pattern_reliability_keys_are_independent_and_unsorted_input_is_handled() -> None:
    df = _fixture()
    hits = [_hit(K.HAMMER, 3, df), _hit(K.DOJI, 1, df), _hit(K.HAMMER, 2, df)]

    result = pattern_reliability(df, hits, horizon=3, min_samples=1)

    # Hammer hits sorted to t2, t3 -> t3 is within 3 of t2 and skipped: n == 1 (+.03).
    assert set(result) == {K.HAMMER, K.DOJI}
    assert result[K.HAMMER].n == 1
    assert result[K.HAMMER].mean_return == pytest.approx(0.03)
    assert result[K.DOJI].n == 1


def test_pattern_reliability_hit_without_forward_bars_gives_empty_stats() -> None:
    df = _fixture()

    stats = pattern_reliability(df, [_hit(K.HAMMER, 11, df)], horizon=3)[K.HAMMER]

    assert stats.n == 0
    assert stats.hit_rate is None
    assert stats.wilson_low is None
    assert stats.mean_return is None
    assert stats.median_return is None
    assert stats.edge is None
    assert stats.sufficient is False


def test_pattern_reliability_entry_is_next_open_and_zero_return_is_not_up() -> None:
    # horizon 2. t0: entry open[1] = 50, exit close[2] = 55 -> +0.10.
    # t1: entry open[2] = 60, exit close[3] = 60 -> exactly 0 (not up).
    df = frame(
        [(100.0, 120.0, 40.0, 100.0), (50.0, 70.0, 40.0, 51.0), (60.0, 70.0, 50.0, 55.0)]
        + [(70.0, 80.0, 50.0, 60.0)]
    )
    hits = [_hit(K.HAMMER, 0, df), _hit(K.INVERTED_HAMMER, 1, df)]

    result = pattern_reliability(df, hits, horizon=2, min_samples=1, trend=_ctx(df, "down"))

    assert result[K.HAMMER].mean_return == pytest.approx(0.10)
    assert result[K.INVERTED_HAMMER].mean_return == pytest.approx(0.0)
    assert result[K.INVERTED_HAMMER].up_count == 0
    assert result[K.INVERTED_HAMMER].success_count == 0
    assert result[K.HAMMER].base_up_rate == pytest.approx(0.5)  # only t0 is up of {t0, t1}


def test_pattern_reliability_no_eligible_bars_leaves_base_rates_unknown() -> None:
    df = _fixture().iloc[:3]

    stats = pattern_reliability(df, [_hit(K.HAMMER, 0, df)], horizon=5)[K.HAMMER]

    assert stats.base_up_rate is None
    assert stats.base_rate is None
    assert stats.n == 0


def test_pattern_reliability_rejects_non_positive_horizon() -> None:
    with pytest.raises(ValueError, match="horizon"):
        pattern_reliability(_fixture(), [], horizon=0)


def test_pattern_reliability_no_hits_returns_empty_mapping() -> None:
    assert pattern_reliability(_fixture(), []) == {}


def test_pattern_reliability_bearish_base_rate_is_share_of_negative_returns_with_ticks() -> None:
    # Flat open of 100 and mostly-100 closes: most forward returns are exactly 0 (a tick-size
    # market). 1 - up-rate would count those zeros as "down"; the base rate must not.
    closes = [100.0] * 60
    for i in range(0, 60, 7):
        closes[i] = 101.0
    for i in range(3, 60, 11):
        closes[i] = 99.0
    df = frame([(100.0, 102.0, 98.0, c) for c in closes])
    horizon = 3
    rets = [closes[t + horizon] / 100.0 - 1.0 for t in range(len(closes) - horizon)]
    share_down = sum(r < 0 for r in rets) / len(rets)
    share_up = sum(r > 0 for r in rets) / len(rets)
    assert 1.0 - share_up > share_down + 0.3  # guard: the old formula would be far off

    stats = pattern_reliability(
        df, [_hit(K.EVENING_STAR, 10, df)], horizon=horizon, trend=_ctx(df, "up")
    )[K.EVENING_STAR]

    assert stats.base_down_rate == pytest.approx(share_down)
    assert stats.base_rate == pytest.approx(share_down)
    assert stats.base_up_rate == pytest.approx(share_up)


def test_pattern_reliability_default_min_samples_is_fifteen() -> None:
    df = _daily([100.0 + (i % 5) for i in range(200)])
    hits = [_hit(K.DOJI, t, df) for t in range(0, 14 * 5, 5)]  # 14 non-overlapping hits
    more = [*hits, _hit(K.DOJI, 14 * 5, df)]  # 15

    thin = pattern_reliability(df, hits)[K.DOJI]
    enough = pattern_reliability(df, more)[K.DOJI]

    assert (thin.n, thin.sufficient) == (14, False)
    assert (enough.n, enough.sufficient) == (15, True)


def _mean_reverting(n: int = 3000, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = 0.9 * x[i - 1] + rng.normal(0.0, 0.01)
    c = 100.0 * np.exp(x)
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame(
        {
            "open": o,
            "high": np.maximum(o, c) * 1.002,
            "low": np.minimum(o, c) * 0.998,
            "close": c,
            "volume": 1000.0,
        },
        index=pd.bdate_range("2010-01-01", periods=n),
    )


def test_pattern_reliability_context_only_pattern_has_no_edge_on_mean_reverting_series() -> None:
    df = _mean_reverting()
    tc = trend_context(df)
    # A fake "pattern" that fires on every bar in a downtrend and encodes nothing else.
    hits = [_hit(K.HAMMER, t, df) for t in range(len(df)) if trend_is(tc.iloc[t], "down")]
    close, open_ = df["close"].to_numpy(), df["open"].to_numpy()
    unconditional_up = float((close[5:] / open_[1:-4] - 1 > 0).mean())

    stats = pattern_reliability(df, hits)[K.HAMMER]

    assert stats.hit_rate is not None
    assert stats.hit_rate - unconditional_up > 0.1  # the old yardstick would show a big "edge"
    assert stats.edge is not None
    assert abs(stats.edge) < 0.05


def test_pattern_reliability_base_rate_uses_only_bars_in_the_required_context() -> None:
    # Hand fixture: forward ret (horizon 1) is entry open[t+1]=100 vs close[t+1].
    closes = [101.0, 99.0, 101.0, 101.0, 99.0, 100.0]  # ret[t] = closes[t+1]/100 - 1, t = 0..4
    df = frame([(100.0, 102.0, 98.0, c) for c in closes])
    ctx = pd.Series(["down", "down", "up", "none", "up", pd.NA], index=df.index, dtype=object)
    hits = [_hit(K.HAMMER, 0, df), _hit(K.THREE_WHITE_SOLDIERS, 0, df), _hit(K.DOJI, 0, df)]

    result = pattern_reliability(df, hits, horizon=1, trend=ctx)

    # rets: t0 -.01, t1 +.01, t2 +.01, t3 -.01, t4 0.0
    assert result[K.HAMMER].base_up_rate == pytest.approx(0.5)  # down bars: t0, t1
    assert result[K.THREE_WHITE_SOLDIERS].base_up_rate == pytest.approx(1 / 3)  # t0, t1, t3
    assert result[K.DOJI].base_up_rate == pytest.approx(2 / 5)  # every eligible bar
    assert result[K.HAMMER].base_n == 2
