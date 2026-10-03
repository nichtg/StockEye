# ruff: noqa: RUF005
"""Candlestick detection: positive and near-miss fixtures, ordering, thresholds, look-ahead."""

from dataclasses import FrozenInstanceError

import numpy as np
import pandas as pd
import pytest
from candle_fixtures import CTX_LEN, NEGATIVE, POSITIVE, Bar, context, keys_at_last
from hypothesis import given, settings
from technical_refs import frame, ohlc_frames

from app.domain.technical import PATTERNS, PatternHit, PatternKey, PatternThresholds
from app.domain.technical import detect_patterns as detect
from app.domain.technical.candlesticks import Bias

K = PatternKey


@pytest.mark.parametrize(("case", "kind", "pattern", "key"), POSITIVE, ids=[p[0] for p in POSITIVE])
def test_detect_patterns_positive_fixture_fires_on_last_candle(
    case: str, kind: str, pattern: list[Bar], key: PatternKey
) -> None:
    df = frame(context(kind) + pattern)

    hits = [h for h in detect(df) if h.key is key]

    assert [h.index for h in hits] == [len(df) - 1], case
    assert hits[0].date == df.index[-1]
    assert hits[0].bias is PATTERNS[key].bias


@pytest.mark.parametrize(("case", "kind", "pattern", "key"), NEGATIVE, ids=[n[0] for n in NEGATIVE])
def test_detect_patterns_near_miss_fixture_does_not_fire(
    case: str, kind: str, pattern: list[Bar], key: PatternKey
) -> None:
    assert key not in keys_at_last(kind, pattern), case


def test_detect_patterns_only_pattern_bars_fire_in_context_bars() -> None:
    df = frame(context("down") + [(78.5, 79.0, 77.0, 79.0)])

    assert all(h.index >= CTX_LEN for h in detect(df) if h.key is not K.DOJI)


def test_detect_patterns_hits_sorted_by_index_with_several_on_one_bar() -> None:
    # Second bar is both a bullish harami (inside a long bearish bar) and hammer-shaped
    # (body 0.5, lower shadow 1.0, no upper shadow).
    bars = [(80.0, 80.5, 77.0, 77.5), (77.75, 78.25, 76.75, 78.25)]
    df = frame(context("down") + bars + [(100.0, 101.0, 99.0, 100.0)])

    hits = detect(df)

    at_21 = {h.key for h in hits if h.index == CTX_LEN + 1}
    assert {K.HAMMER, K.BULLISH_HARAMI} <= at_21
    assert [h.index for h in hits] == sorted(h.index for h in hits)


def test_detect_patterns_custom_thresholds_change_outcome() -> None:
    bars = [(80.0, 80.25, 79.25, 79.5), (79.625, 79.875, 79.5, 79.75)]
    df = frame(context("down") + bars)

    default = {h.key for h in detect(df) if h.index == CTX_LEN + 1}
    relaxed = {
        h.key for h in detect(df, PatternThresholds(long_body_atr=0.2)) if h.index == CTX_LEN + 1
    }

    assert K.BULLISH_HARAMI not in default
    assert K.BULLISH_HARAMI in relaxed


def test_detect_patterns_prefix_of_history_gives_same_hits() -> None:
    bars = context("down") + [
        (80.0, 80.5, 78.0, 78.5),
        (78.5, 80.5, 78.25, 80.25),
        (80.0, 81.0, 79.0, 80.0),
    ]
    full = detect(frame(bars))

    prefix = detect(frame(bars[:-1]))

    assert prefix == [h for h in full if h.index < len(bars) - 1]


@settings(max_examples=40, deadline=None)
@given(df=ohlc_frames(min_size=25, max_size=50))
def test_detect_patterns_property_future_bars_never_change_earlier_hits(df: pd.DataFrame) -> None:
    k = len(df) - 5
    changed = df.copy()
    changed.loc[changed.index[k:], ["open", "high", "low", "close"]] = np.tile(
        [50.0, 90.0, 10.0, 70.0], (len(df) - k, 1)
    )

    before = [h for h in detect(df) if h.index < k]
    after = [h for h in detect(changed) if h.index < k]

    assert before == after


def test_patterns_registry_covers_all_keys_with_labels_and_bias() -> None:
    assert set(PATTERNS) == set(PatternKey)
    assert PATTERNS[K.BULLISH_ENGULFING].label == "Bullish engulfing"
    assert PATTERNS[K.BULLISH_ENGULFING].bias is Bias.BULLISH
    assert PATTERNS[K.DOJI].bias is Bias.NEUTRAL
    assert PATTERNS[K.EVENING_STAR].bias is Bias.BEARISH
    assert {k: s.candles for k, s in PATTERNS.items() if s.candles == 3} == {
        K.MORNING_STAR: 3,
        K.EVENING_STAR: 3,
        K.THREE_WHITE_SOLDIERS: 3,
        K.THREE_BLACK_CROWS: 3,
    }
    assert all(1 <= s.candles <= 3 for s in PATTERNS.values())


def test_pattern_hit_and_spec_are_frozen() -> None:
    hit = PatternHit(K.DOJI, Bias.NEUTRAL, 3, pd.Timestamp("2024-01-04").to_pydatetime())

    with pytest.raises(FrozenInstanceError):
        hit.index = 4  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        PATTERNS[K.DOJI].label = "x"  # type: ignore[misc]
