# ruff: noqa: DTZ001
"""Regression tests for the fix-round-1 audit findings (each fails on the pre-fix code)."""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest
from technical_refs import frame

from app.domain.technical import (
    PATTERNS,
    Outlook,
    PatternHit,
    PatternKey,
    PatternStats,
    anchored_vwap,
    atr,
    build_outlook,
    detect_patterns,
    pattern_reliability,
    rsi,
    session_vwap,
)
from app.domain.technical.candlesticks import context_allows, trend_context

K = PatternKey
AS_OF = datetime(2024, 3, 1)


def _hit(key: PatternKey, index: int, df: pd.DataFrame | None = None) -> PatternHit:
    stamp = datetime(2024, 1, 1) if df is None else df.index[index].to_pydatetime()
    return PatternHit(key, PATTERNS[key].bias, index, stamp)


def _is(value: object, wanted: str) -> bool:
    return isinstance(value, str) and value == wanted


def _ctx(df: pd.DataFrame, value: str) -> pd.Series:
    return pd.Series(value, index=df.index, dtype=object)


def _daily(closes: list[float]) -> pd.DataFrame:
    return frame([(c, c + 1.0, c - 1.0, c) for c in closes])


def _growth(n: int = 45) -> list[float]:
    return [100.0 * 1.03**i for i in range(n)]


def _stats(
    key: PatternKey,
    *,
    n: int = 18,
    success: int = 14,
    base: float = 0.55,
    low: float = 0.6,
    sufficient: bool = True,
) -> PatternStats:
    hit = success / n
    return PatternStats(
        key=key,
        n=n,
        up_count=success,
        success_count=success,
        hit_rate=hit,
        wilson_low=low,
        wilson_high=0.95,
        mean_return=0.01,
        median_return=0.01,
        base_up_rate=base,
        base_rate=base,
        edge=hit - base,
        sufficient=sufficient,
    )


# ------------------------------------------------------------------ C1: bearish base rate


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


# ------------------------------------------------------------------ M5: ties


def test_build_outlook_constant_prices_is_neutral_with_score_zero() -> None:
    df = frame([(100.0, 100.0, 100.0, 100.0)] * 60)

    out = build_outlook(df, [], {}, 100.0, AS_OF)

    assert out.lean == "neutral"
    assert out.score == 0.0
    by_key = {s.key: s for s in out.signals}
    for key in ("rsi14", "ema_cross", "macd_momentum", "vwap"):
        assert by_key[key].direction == 0
        assert by_key[key].weight > 0  # the tie still counts its weight


# ------------------------------------------------------------------ M6: credible patterns only


def test_build_outlook_pattern_counts_only_when_wilson_low_beats_base_rate() -> None:
    credible = {K.HAMMER: _stats(K.HAMMER, low=0.56)}
    not_credible = {K.HAMMER: _stats(K.HAMMER, low=0.55)}  # equals the base rate: not above it
    daily = _daily(_growth())

    yes = build_outlook(daily, [_hit(K.HAMMER, 1)], credible, None, AS_OF)
    no = build_outlook(daily, [_hit(K.HAMMER, 1)], not_credible, None, AS_OF)

    sig_yes = next(s for s in yes.signals if s.key == "patterns")
    sig_no = next(s for s in no.signals if s.key == "patterns")
    assert sig_yes.direction == 1
    assert sig_yes.weight == pytest.approx(min((14 / 18 - 0.55) / 0.2, 1.0))
    assert (sig_no.direction, sig_no.weight) == (0, 0.0)


def test_build_outlook_pattern_detail_explains_reliable_and_unclear_outcomes() -> None:
    daily = _daily(_growth())
    rel = {K.BULLISH_ENGULFING: _stats(K.BULLISH_ENGULFING)}
    good = build_outlook(daily, [_hit(K.BULLISH_ENGULFING, 1)], rel, None, AS_OF)
    weak = build_outlook(
        daily,
        [_hit(K.BULLISH_ENGULFING, 1)],
        {K.BULLISH_ENGULFING: _stats(K.BULLISH_ENGULFING, low=0.4)},
        None,
        AS_OF,
    )

    d_good = next(s.detail for s in good.signals if s.key == "patterns")
    d_weak = next(s.detail for s in weak.signals if s.key == "patterns")

    assert "Bullish engulfing has been reliable for this stock" in d_good
    assert "higher a week later 14 of 18 times vs 55% normally" in d_good
    assert "seen 18 times, but not clearly better than a typical week" in d_weak


def test_build_outlook_bearish_pattern_detail_says_lower() -> None:
    rel = {K.EVENING_STAR: _stats(K.EVENING_STAR)}

    out = build_outlook(_daily(_growth()), [_hit(K.EVENING_STAR, 1)], rel, None, AS_OF)

    sig = next(s for s in out.signals if s.key == "patterns")
    assert sig.direction == -1
    assert "lower a week later 14 of 18 times" in sig.detail


def test_pattern_reliability_default_min_samples_is_fifteen() -> None:
    df = _daily([100.0 + (i % 5) for i in range(200)])
    hits = [_hit(K.DOJI, t, df) for t in range(0, 14 * 5, 5)]  # 14 non-overlapping hits
    more = [*hits, _hit(K.DOJI, 14 * 5, df)]  # 15

    thin = pattern_reliability(df, hits)[K.DOJI]
    enough = pattern_reliability(df, more)[K.DOJI]

    assert (thin.n, thin.sufficient) == (14, False)
    assert (enough.n, enough.sufficient) == (15, True)


# ------------------------------------------------------------------ M7: conditional base rate


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
    hits = [_hit(K.HAMMER, t, df) for t in range(len(df)) if _is(tc.iloc[t], "down")]
    close, open_ = df["close"].to_numpy(), df["open"].to_numpy()
    unconditional_up = float((close[5:] / open_[1:-4] - 1 > 0).mean())

    stats = pattern_reliability(df, hits)[K.HAMMER]

    assert stats.hit_rate is not None
    assert stats.hit_rate - unconditional_up > 0.1  # the old yardstick would show a big "edge"
    assert stats.edge is not None
    assert abs(stats.edge) < 0.05


def test_trend_context_values_use_only_earlier_bars() -> None:
    df = frame([(100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i) for i in range(30)])
    changed = df.copy()
    changed.iloc[20, :4] = [500.0, 600.0, 400.0, 550.0]  # a spike at bar 20

    base, alt = trend_context(df), trend_context(changed)

    assert pd.isna(base.iloc[0])
    assert _is(base.iloc[25], "up")
    for s in range(21):  # context at s uses bars <= s-1, so bar 20 only affects s >= 21
        both_unknown = pd.isna(base.iloc[s]) and pd.isna(alt.iloc[s])
        assert both_unknown or base.iloc[s] == alt.iloc[s]


def test_pattern_specs_declare_their_required_trend_context() -> None:
    assert PATTERNS[K.DOJI].context == "any"
    assert PATTERNS[K.HAMMER].context == "down"
    assert PATTERNS[K.SHOOTING_STAR].context == "up"
    assert PATTERNS[K.THREE_WHITE_SOLDIERS].context == "down_or_none"
    assert PATTERNS[K.THREE_BLACK_CROWS].context == "up_or_none"
    assert context_allows("down_or_none", "none") is True
    assert context_allows("down_or_none", "up") is False
    assert context_allows("down", pd.NA) is False
    assert context_allows("any", pd.NA) is True


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


# ------------------------------------------------------------------ M8: NaN handling


def _with_nan(column: str = "close", at: int = 12) -> pd.DataFrame:
    df = _daily([100.0 + i for i in range(40)])
    df.iloc[at, df.columns.get_loc(column)] = np.nan  # type: ignore[index]
    return df


@pytest.mark.parametrize("column", ["open", "high", "low", "close"])
def test_functions_taking_a_frame_reject_nan_prices_naming_the_date(column: str) -> None:
    df = _with_nan(column)
    stamp = str(df.index[12])
    hit = _hit(K.DOJI, 1, df)

    for call in (
        lambda: detect_patterns(df),
        lambda: pattern_reliability(df, [hit]),
        lambda: build_outlook(df, [], {}, None, AS_OF),
        lambda: atr(df),
        lambda: session_vwap(df),
        lambda: anchored_vwap(df, df.index[0].to_pydatetime()),
    ):
        with pytest.raises(ValueError, match="price history contains missing values at") as exc:
            call()
        assert stamp in str(exc.value)


def test_functions_taking_a_frame_reject_a_non_increasing_index() -> None:
    df = _daily([100.0 + i for i in range(40)])
    df = df.iloc[[*range(10), 9, *range(11, 40)]]  # duplicate label

    with pytest.raises(ValueError, match="strictly increasing"):
        detect_patterns(df)
    with pytest.raises(ValueError, match="strictly increasing"):
        build_outlook(df.iloc[::-1], [], {}, None, AS_OF)


def test_rsi_propagates_nan_instead_of_reading_it_as_no_change() -> None:
    close = pd.Series([100.0 + (i % 3) for i in range(40)])
    close.iloc[20] = np.nan

    out = rsi(close, 14)

    assert not out.iloc[:14].notna().any()
    assert out.iloc[14:20].notna().all()
    assert out.iloc[20:].isna().all()


# ------------------------------------------------------------------ minor findings


def test_build_outlook_doji_hit_is_indecision_with_zero_weight_not_thin_history() -> None:
    out = build_outlook(_daily(_growth()), [_hit(K.DOJI, 1)], {}, None, AS_OF)

    sig = next(s for s in out.signals if s.key == "patterns")
    assert (sig.direction, sig.weight) == (0, 0.0)
    assert "Doji: indecision pattern, no directional signal" in sig.detail
    assert "not enough" not in sig.detail


def test_build_outlook_rsi_detail_has_one_decimal() -> None:
    closes = [100.0 + (i % 2) * 1.5 + (i // 7) * 0.2 for i in range(40)]

    out = build_outlook(_daily(closes), [], {}, None, AS_OF)

    detail = next(s.detail for s in out.signals if s.key == "rsi14")
    value = detail.split("RSI is ")[1].split(",")[0]
    assert len(value.split(".")[1]) == 1


def test_outlook_exposes_typical_week_range_and_coverage() -> None:
    out: Outlook = build_outlook(_daily(_growth()), [], {}, None, AS_OF)

    assert out.expected_range_coverage == 0.9
    assert out.typical_week_range == out.expected_range
    assert out.expected_range is not None


def test_anchored_vwap_rejects_timezone_aware_anchor() -> None:
    df = _daily([100.0 + i for i in range(10)])

    with pytest.raises(ValueError, match="timezone-aware"):
        anchored_vwap(df, pd.Timestamp("2024-01-03", tz="UTC"))
