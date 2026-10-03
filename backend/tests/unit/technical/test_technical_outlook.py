# ruff: noqa: RUF005, DTZ001
"""Outlook tests: signal rules, weights, score arithmetic and lean thresholds."""

import math
from datetime import datetime

import pandas as pd
import pytest
from technical_refs import frame, ref_atr, ref_ema, ref_macd, ref_rsi

from app.domain.technical import (
    Outlook,
    PatternHit,
    PatternKey,
    PatternStats,
    Signal,
    build_outlook,
)
from app.domain.technical.candlesticks import PATTERNS

K = PatternKey
AS_OF = datetime(2024, 3, 1)


def _daily(closes: list[float]) -> pd.DataFrame:
    """Bars with open = close and a +/-1 wick, so every true range is 2 (steady ramps)."""
    return frame([(c, c + 1.0, c - 1.0, c) for c in closes])


def _growth(n: int = 45, rate: float = 1.03) -> list[float]:
    return [100.0 * rate**i for i in range(n)]


def _hit(key: PatternKey, index: int = 0) -> PatternHit:
    return PatternHit(key, PATTERNS[key].bias, index, datetime(2024, 1, 1))


def _stats(
    key: PatternKey, edge: float | None, *, sufficient: bool = True, credible: bool = True
) -> PatternStats:
    """Stats with base rate 0.5, hit rate 0.5 + edge and a Wilson bound above/below the base."""
    return PatternStats(
        key=key,
        n=10 if sufficient else 2,
        up_count=5,
        success_count=None if edge is None else round(10 * (0.5 + edge)),
        hit_rate=None if edge is None else 0.5 + edge,
        wilson_low=(0.51 if credible else 0.3) if edge is not None else None,
        wilson_high=0.8,
        mean_return=0.01,
        median_return=0.01,
        base_up_rate=0.5,
        base_rate=None if edge is None else 0.5,
        edge=edge,
        sufficient=sufficient,
    )


def _edge_stats(
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


def _sig(outlook: Outlook, key: str) -> Signal:
    return next(s for s in outlook.signals if s.key == key)


def _keys(outlook: Outlook) -> list[str]:
    return [s.key for s in outlook.signals]


# ---------------------------------------------------------------- indicator signals


def test_build_outlook_uptrend_ramp_flags_rsi_overbought_and_ema_up_with_hand_range() -> None:
    closes = [100.0 + i for i in range(40)]  # RSI = 100, ema9 > ema21, every TR = 2 so ATR = 2

    out = build_outlook(_daily(closes), [], {}, None, AS_OF)

    rsi_sig = _sig(out, "rsi14")
    assert (rsi_sig.direction, rsi_sig.weight) == (-1, 0.75)
    assert "RSI is 100" in rsi_sig.detail
    assert "overbought" in rsi_sig.detail
    ema_sig = _sig(out, "ema_cross")
    assert (ema_sig.direction, ema_sig.weight) == (1, 0.75)
    assert "no fresh cross" in ema_sig.detail
    assert out.last_close == 139.0
    assert out.expected_range is not None
    assert out.expected_range[0] == pytest.approx(139.0 - 2.0 * math.sqrt(5))
    assert out.expected_range[1] == pytest.approx(139.0 + 2.0 * math.sqrt(5))
    assert out.as_of == AS_OF


def test_build_outlook_downtrend_ramp_flags_rsi_oversold_and_ema_down() -> None:
    closes = [200.0 - i for i in range(40)]

    out = build_outlook(_daily(closes), [], {}, None, AS_OF)

    rsi_sig = _sig(out, "rsi14")
    assert (rsi_sig.direction, rsi_sig.weight) == (1, 0.75)
    assert "oversold" in rsi_sig.detail
    assert _sig(out, "ema_cross").direction == -1


def test_build_outlook_rsi_between_thresholds_is_neutral_with_weight_kept() -> None:
    closes = [100.0 + (i % 2) for i in range(40)]  # alternating +1/-1 -> RSI stays near 50

    out = build_outlook(_daily(closes), [], {}, None, AS_OF)

    rsi_sig = _sig(out, "rsi14")
    assert rsi_sig.direction == 0
    assert rsi_sig.weight == 0.75
    assert f"RSI is {ref_rsi(closes, 14)[-1]:.0f}" in rsi_sig.detail


def test_build_outlook_signals_match_independent_reference_series() -> None:
    closes = [100 + 6 * math.sin(i / 4) + 0.15 * i for i in range(70)]
    df = _daily(closes)
    rsi_now = ref_rsi(closes, 14)[-1]
    fast, slow = ref_ema(closes, 9), ref_ema(closes, 21)
    hist = ref_macd(closes, 12, 26, 9)[2]

    out = build_outlook(df, [], {}, None, AS_OF)

    assert _sig(out, "rsi14").direction == (-1 if rsi_now > 70 else 1 if rsi_now < 30 else 0)
    assert _sig(out, "ema_cross").direction == (1 if fast[-1] > slow[-1] else -1)
    assert _sig(out, "macd_momentum").direction == (1 if hist[-1] > hist[-2] else -1)
    ref = ref_atr([c + 1 for c in closes], [c - 1 for c in closes], closes, 14)[-1]
    assert out.expected_range is not None
    assert out.expected_range[1] - closes[-1] == pytest.approx(ref * math.sqrt(5))


def test_build_outlook_fresh_ema_cross_within_three_sessions_is_mentioned() -> None:
    # 30 bars of falling price, then a sharp reversal on the last bar flips ema9 above ema21.
    closes = [200.0 - i for i in range(30)] + [230.0]
    fast, slow = ref_ema(closes, 9), ref_ema(closes, 21)
    assert fast[-2] < slow[-2]  # guards the fixture: it was below before the last bar
    assert fast[-1] > slow[-1]  # ... and is above after it

    out = build_outlook(_daily(closes), [], {}, None, AS_OF)

    ema_sig = _sig(out, "ema_cross")
    assert ema_sig.direction == 1
    assert "cross happened within the last 3 sessions" in ema_sig.detail


def test_build_outlook_old_ema_cross_is_not_called_fresh() -> None:
    closes = [200.0 - i for i in range(30)] + [230.0] + [231.0, 232.0, 233.0, 234.0]
    fast, slow = ref_ema(closes, 9), ref_ema(closes, 21)
    assert fast[-5] > slow[-5] > 0 and fast[-6] < slow[-6]  # cross was 4 bars ago

    out = build_outlook(_daily(closes), [], {}, None, AS_OF)

    assert "no fresh cross" in _sig(out, "ema_cross").detail


def test_build_outlook_macd_momentum_rising_histogram_is_bullish() -> None:
    out = build_outlook(_daily(_growth()), [], {}, None, AS_OF)

    sig = _sig(out, "macd_momentum")
    assert (sig.direction, sig.weight) == (1, 0.5)


def test_build_outlook_macd_momentum_falling_histogram_is_bearish() -> None:
    closes = _growth(40) + [150.0, 120.0, 100.0]
    hist = ref_macd(closes, 12, 26, 9)[2]
    assert hist[-1] < hist[-2]  # guards the fixture

    out = build_outlook(_daily(closes), [], {}, None, AS_OF)

    assert _sig(out, "macd_momentum").direction == -1


def test_build_outlook_vwap_above_and_below_and_equal() -> None:
    df = _daily([100.0 + i for i in range(40)])  # close 139

    above = _sig(build_outlook(df, [], {}, 130.0, AS_OF), "vwap")
    below = _sig(build_outlook(df, [], {}, 150.0, AS_OF), "vwap")
    equal = _sig(build_outlook(df, [], {}, 139.0, AS_OF), "vwap")

    assert (above.direction, above.weight) == (1, 0.5)
    assert below.direction == -1
    assert (equal.direction, equal.weight) == (0, 0.5)  # a tie votes 0 but keeps its weight
    assert "130.00" in above.detail


def test_build_outlook_without_vwap_skips_the_signal() -> None:
    out = build_outlook(_daily(_growth()), [], {}, None, AS_OF)

    assert "vwap" not in _keys(out)


# ---------------------------------------------------------------- pattern signal


def test_build_outlook_no_recent_hits_pattern_signal_has_zero_weight() -> None:
    out = build_outlook(_daily(_growth()), [], {}, None, AS_OF)

    sig = _sig(out, "patterns")
    assert (sig.direction, sig.weight) == (0, 0.0)
    assert "No candlestick patterns" in sig.detail


def test_build_outlook_bullish_pattern_with_edge_scales_strength_by_edge_over_point_two() -> None:
    rel = {K.HAMMER: _stats(K.HAMMER, 0.1)}  # strength = 0.1 / 0.2 = 0.5

    sig = _sig(build_outlook(_daily(_growth()), [_hit(K.HAMMER)], rel, None, AS_OF), "patterns")

    assert sig.direction == 1
    assert sig.weight == pytest.approx(0.5)
    assert "Hammer" in sig.detail


def test_build_outlook_bearish_pattern_strength_is_capped_at_one() -> None:
    rel = {K.EVENING_STAR: _stats(K.EVENING_STAR, 0.5)}

    sig = _sig(
        build_outlook(_daily(_growth()), [_hit(K.EVENING_STAR)], rel, None, AS_OF), "patterns"
    )

    assert sig.direction == -1
    assert sig.weight == pytest.approx(1.0)


def test_build_outlook_opposing_patterns_net_out_by_signed_mean_strength() -> None:
    rel = {K.HAMMER: _stats(K.HAMMER, 0.2), K.EVENING_STAR: _stats(K.EVENING_STAR, 0.1)}
    hits = [_hit(K.HAMMER), _hit(K.EVENING_STAR)]  # +1.0 and -0.5 -> mean +0.25

    sig = _sig(build_outlook(_daily(_growth()), hits, rel, None, AS_OF), "patterns")

    assert sig.direction == 1
    assert sig.weight == pytest.approx(0.25)


def test_build_outlook_insufficient_history_pattern_gets_zero_weight_and_says_so() -> None:
    rel = {K.HAMMER: _stats(K.HAMMER, 0.3, sufficient=False)}

    sig = _sig(build_outlook(_daily(_growth()), [_hit(K.HAMMER)], rel, None, AS_OF), "patterns")

    assert (sig.direction, sig.weight) == (0, 0.0)
    assert "not enough past occurrences" in sig.detail


def test_build_outlook_pattern_missing_from_reliability_counts_as_insufficient() -> None:
    sig = _sig(build_outlook(_daily(_growth()), [_hit(K.HAMMER)], {}, None, AS_OF), "patterns")

    assert sig.weight == 0.0
    assert "not enough past occurrences" in sig.detail


def test_build_outlook_pattern_without_edge_is_ignored() -> None:
    rel = {K.HAMMER: _stats(K.HAMMER, -0.1, credible=False), K.DOJI: _stats(K.DOJI, None)}

    sig = _sig(
        build_outlook(_daily(_growth()), [_hit(K.HAMMER), _hit(K.DOJI)], rel, None, AS_OF),
        "patterns",
    )

    assert sig.weight == 0.0


def test_build_outlook_sufficient_pattern_with_non_positive_edge_gets_zero_weight() -> None:
    rel = {K.HAMMER: _stats(K.HAMMER, -0.1, credible=False)}

    sig = _sig(build_outlook(_daily(_growth()), [_hit(K.HAMMER)], rel, None, AS_OF), "patterns")

    assert sig.weight == 0.0
    assert "not clearly better than a typical week" in sig.detail


def test_build_outlook_mixed_sufficient_and_thin_patterns_notes_ignored_ones() -> None:
    rel = {K.HAMMER: _stats(K.HAMMER, 0.2), K.DOJI: _stats(K.DOJI, 0.3, sufficient=False)}
    hits = [_hit(K.HAMMER), _hit(K.DOJI)]

    sig = _sig(build_outlook(_daily(_growth()), hits, rel, None, AS_OF), "patterns")

    assert sig.weight == pytest.approx(1.0)
    assert "Doji" in sig.detail


# ---------------------------------------------------------------- score and lean


def test_build_outlook_score_is_weighted_mean_of_directions_over_positive_weights() -> None:
    # growth series: RSI 100 (-1, .75), EMA up (+1, .75), MACD rising (+1, .5),
    # VWAP below close (+1, .5), pattern signal weight 0 (excluded from the denominator).
    out = build_outlook(_daily(_growth()), [], {}, 100.0, AS_OF)

    assert out.score == pytest.approx((-0.75 + 0.75 + 0.5 + 0.5) / 2.5)
    assert out.lean == "bullish"


def test_build_outlook_score_exactly_at_plus_quarter_is_bullish() -> None:
    # without vwap: (-.75 + .75 + .5) / (.75 + .75 + .5) = 0.25
    out = build_outlook(_daily(_growth()), [], {}, None, AS_OF)

    assert out.score == 0.25
    assert out.lean == "bullish"


def test_build_outlook_score_exactly_at_minus_quarter_is_bearish() -> None:
    # decay: RSI 0 (+1, .75), EMA down (-1, .75), MACD falling (-1, .5): -0.5 / 2.0
    out = build_outlook(_daily([100.0 * 0.97**i for i in range(45)]), [], {}, None, AS_OF)

    assert out.score == -0.25
    assert out.lean == "bearish"


def test_build_outlook_score_between_thresholds_is_neutral() -> None:
    # same as the +0.25 case but a bearish VWAP (-.5) pulls it to (0.5 - 0.5) / 2.5 = 0
    out = build_outlook(_daily(_growth()), [], {}, 10_000.0, AS_OF)

    assert out.score == pytest.approx(0.0)
    assert out.lean == "neutral"


def test_build_outlook_pattern_weight_enters_the_score() -> None:
    rel = {K.HAMMER: _stats(K.HAMMER, 0.2)}  # strength 1 -> +1.0 on weight 1.0

    out = build_outlook(_daily(_growth()), [_hit(K.HAMMER)], rel, None, AS_OF)

    assert out.score == pytest.approx((1.0 - 0.75 + 0.75 + 0.5) / 3.0)


# ---------------------------------------------------------------- degenerate inputs


def test_build_outlook_short_history_omits_warmup_signals_and_range() -> None:
    out = build_outlook(_daily([100.0, 101.0, 102.0]), [], {}, None, AS_OF)

    assert _keys(out) == ["patterns"]
    assert out.score == 0.0
    assert out.lean == "neutral"
    assert out.expected_range is None
    assert out.last_close == 102.0


def test_build_outlook_single_bar_has_no_macd_signal() -> None:
    out = build_outlook(_daily([100.0]), [], {}, 99.0, AS_OF)

    assert "macd_momentum" not in _keys(out)
    assert _sig(out, "vwap").direction == 1


def test_build_outlook_empty_history_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        build_outlook(_daily([]), [], {}, None, AS_OF)


def test_outlook_and_signal_are_frozen() -> None:
    out = build_outlook(_daily(_growth()), [], {}, None, AS_OF)

    with pytest.raises(AttributeError):
        out.score = 1.0  # type: ignore[misc]
    with pytest.raises(AttributeError):
        out.signals[0].weight = 2.0  # type: ignore[misc]


def test_build_outlook_constant_prices_is_neutral_with_score_zero() -> None:
    df = frame([(100.0, 100.0, 100.0, 100.0)] * 60)

    out = build_outlook(df, [], {}, 100.0, AS_OF)

    assert out.lean == "neutral"
    assert out.score == 0.0
    by_key = {s.key: s for s in out.signals}
    for key in ("rsi14", "ema_cross", "macd_momentum", "vwap"):
        assert by_key[key].direction == 0
        assert by_key[key].weight > 0  # the tie still counts its weight


def test_build_outlook_pattern_counts_only_when_wilson_low_beats_base_rate() -> None:
    credible = {K.HAMMER: _edge_stats(K.HAMMER, low=0.56)}
    not_credible = {K.HAMMER: _edge_stats(K.HAMMER, low=0.55)}  # equals the base rate: not above it
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
    rel = {K.BULLISH_ENGULFING: _edge_stats(K.BULLISH_ENGULFING)}
    good = build_outlook(daily, [_hit(K.BULLISH_ENGULFING, 1)], rel, None, AS_OF)
    weak = build_outlook(
        daily,
        [_hit(K.BULLISH_ENGULFING, 1)],
        {K.BULLISH_ENGULFING: _edge_stats(K.BULLISH_ENGULFING, low=0.4)},
        None,
        AS_OF,
    )

    d_good = next(s.detail for s in good.signals if s.key == "patterns")
    d_weak = next(s.detail for s in weak.signals if s.key == "patterns")

    assert "Bullish engulfing has been reliable for this stock" in d_good
    assert "higher a week later 14 of 18 times vs 55% normally" in d_good
    assert "seen 18 times, but not clearly better than a typical week" in d_weak


def test_build_outlook_bearish_pattern_detail_says_lower() -> None:
    rel = {K.EVENING_STAR: _edge_stats(K.EVENING_STAR)}

    out = build_outlook(_daily(_growth()), [_hit(K.EVENING_STAR, 1)], rel, None, AS_OF)

    sig = next(s for s in out.signals if s.key == "patterns")
    assert sig.direction == -1
    assert "lower a week later 14 of 18 times" in sig.detail


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
