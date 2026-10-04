"""Indicator tests: hand-computed fixtures, reference loops, and no-look-ahead properties."""

import math
from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from technical_refs import (
    frame,
    ohlc_frames,
    ref_atr,
    ref_bollinger,
    ref_ema,
    ref_macd,
    ref_rsi,
)

from app.domain.technical import (
    anchored_vwap,
    atr,
    bollinger,
    ema,
    macd,
    rsi,
    session_vwap,
    sma,
)

NAN = float("nan")


def _daily(closes: list[float]) -> pd.DataFrame:
    return frame([(c, c + 1.0, c - 1.0, c) for c in closes])


def _series(values: list[float]) -> pd.Series:
    return pd.Series(values, index=pd.bdate_range("2024-01-01", periods=len(values)), dtype=float)


def _assert_values(actual: pd.Series, expected: list[float], tol: float = 1e-9) -> None:
    got = actual.to_numpy(dtype=float)
    assert len(got) == len(expected)
    for g, e in zip(got, expected, strict=True):
        if math.isnan(e):
            assert math.isnan(g), f"expected NaN, got {g}"
        else:
            assert g == pytest.approx(e, abs=tol)


# ---------------------------------------------------------------- SMA / EMA


def test_sma_period_three_matches_hand_values_and_warms_up_with_nan() -> None:
    result = sma(_series([1, 2, 3, 4, 5, 6]), 3)

    _assert_values(result, [NAN, NAN, 2, 3, 4, 5])


def test_sma_keeps_input_index() -> None:
    close = _series([1, 2, 3, 4])

    assert sma(close, 2).index.equals(close.index)


def test_ema_is_seeded_with_sma_then_recurses() -> None:
    # period 3 -> alpha 0.5. seed idx2 = (10+11+12)/3 = 11.
    # idx3 = .5*11 + .5*11 = 11; idx4 = .5*13 + .5*11 = 12.
    result = ema(_series([10, 11, 12, 11, 13]), 3)

    _assert_values(result, [NAN, NAN, 11, 11, 12])


def test_ema_matches_reference_loop_on_longer_series() -> None:
    x = [44.0, 44.3, 44.1, 43.6, 44.3, 44.8, 45.1, 45.4, 45.8, 46.1, 45.9, 46.0, 46.4, 46.2]

    _assert_values(ema(_series(x), 5), ref_ema(x, 5))


def test_ema_shorter_than_period_is_all_nan() -> None:
    assert ema(_series([1, 2]), 3).isna().all()


def test_ema_all_nan_input_stays_nan() -> None:
    assert ema(_series([NAN, NAN, NAN]), 2).isna().all()


@pytest.mark.parametrize("fn", [sma, ema, rsi])
def test_indicators_reject_non_positive_period(fn: Callable[[pd.Series, int], pd.Series]) -> None:
    with pytest.raises(ValueError, match="period"):
        fn(_series([1, 2, 3]), 0)


# ---------------------------------------------------------------- RSI


def test_rsi_wilder_period_three_matches_hand_values() -> None:
    # changes: +1 -1 +2 -1 +2. First window (3 changes): gain=(1+0+2)/3=1, loss=(0+1+0)/3=1/3.
    # idx3: RS=3 -> 75.
    # idx4 (-1): gain=(1*2+0)/3=2/3, loss=(1/3*2+1)/3=5/9, RS=6/5 -> 100-100/2.2.
    # idx5 (+2): gain=(2/3*2+2)/3=10/9, loss=(5/9*2)/3=10/27, RS=3 -> 75.
    result = rsi(_series([10, 11, 10, 12, 11, 13]), 3)

    _assert_values(result, [NAN, NAN, NAN, 75.0, 100 - 100 / 2.2, 75.0])


def test_rsi_all_gains_is_100() -> None:
    _assert_values(rsi(_series([1, 2, 3, 4, 5]), 3), [NAN, NAN, NAN, 100, 100])


def test_rsi_all_losses_is_0() -> None:
    _assert_values(rsi(_series([5, 4, 3, 2, 1]), 3), [NAN, NAN, NAN, 0, 0])


def test_rsi_flat_prices_is_50() -> None:
    _assert_values(rsi(_series([7, 7, 7, 7, 7]), 3), [NAN, NAN, NAN, 50, 50])


def test_rsi_series_not_longer_than_period_is_all_nan() -> None:
    assert rsi(_series([1, 2, 3]), 3).isna().all()


def test_rsi_matches_reference_loop() -> None:
    x = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61]
    x += [46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64, 46.21, 46.25, 45.71, 46.45, 45.78]

    _assert_values(rsi(_series(x), 14), ref_rsi(x, 14))


# ---------------------------------------------------------------- MACD


def test_macd_hand_fixture_fast2_slow3_signal2() -> None:
    # ema2 (alpha 2/3, seed idx1 = 1.5): 3.16667, 5.72222, 9.24074, 13.74691 at idx2..5
    # ema3 (alpha 1/2, seed idx2 = 7/3):  2.33333, 4.66667, 7.83333, 11.91667
    # macd idx2..5: 0.83333, 1.05556, 1.40741, 1.83025
    # signal (alpha 2/3) seeded at idx3 = mean(0.83333, 1.05556) = 0.94444, then 1.25309, 1.63786
    result = macd(_series([1, 2, 4, 7, 11, 16]), fast=2, slow=3, signal=2)

    _assert_values(result["macd"], [NAN, NAN, 0.83333, 1.05556, 1.40741, 1.83025], tol=1e-4)
    _assert_values(result["signal"], [NAN, NAN, NAN, 0.94444, 1.25309, 1.63786], tol=1e-4)
    _assert_values(result["histogram"], [NAN, NAN, NAN, 0.11111, 0.15432, 0.19239], tol=1e-4)
    assert list(result.columns) == ["macd", "signal", "histogram"]


def test_macd_default_parameters_match_reference_loop() -> None:
    x = [100 + 5 * math.sin(i / 3) + i * 0.2 for i in range(70)]
    line, signal, hist = ref_macd(x, 12, 26, 9)

    result = macd(_series(x))

    _assert_values(result["macd"], line)
    _assert_values(result["signal"], signal)
    _assert_values(result["histogram"], hist)
    # warm-up: macd starts at idx 25, signal at 25 + 8 = 33
    assert result["macd"].first_valid_index() == result.index[25]
    assert result["signal"].first_valid_index() == result.index[33]


# ---------------------------------------------------------------- Bollinger


def test_bollinger_uses_population_std() -> None:
    # Textbook set with mean 5 and population std exactly 2 (sample std would be 2.138).
    result = bollinger(_series([2, 4, 4, 4, 5, 5, 7, 9]), period=8, k=2.0)

    assert result["middle"].iloc[-1] == pytest.approx(5.0)
    assert result["upper"].iloc[-1] == pytest.approx(9.0)
    assert result["lower"].iloc[-1] == pytest.approx(1.0)
    assert result["middle"].iloc[:-1].isna().all()


def test_bollinger_period_three_hand_values() -> None:
    # window [1,2,3]: mean 2, population variance 2/3 -> std 0.816497, k=1.5.
    result = bollinger(_series([1, 2, 3, 4]), period=3, k=1.5)

    std = math.sqrt(2 / 3)
    _assert_values(result["middle"], [NAN, NAN, 2, 3])
    _assert_values(result["upper"], [NAN, NAN, 2 + 1.5 * std, 3 + 1.5 * std])
    _assert_values(result["lower"], [NAN, NAN, 2 - 1.5 * std, 3 - 1.5 * std])


def test_bollinger_matches_reference() -> None:
    x = [10 + (i * 7 % 5) + i * 0.1 for i in range(30)]
    ref = ref_bollinger(x, 20, 2.0)

    result = bollinger(_series(x))

    _assert_values(result["middle"], [r[0] for r in ref])
    _assert_values(result["upper"], [r[1] for r in ref])
    _assert_values(result["lower"], [r[2] for r in ref])


# ---------------------------------------------------------------- ATR


def _atr_frame() -> pd.DataFrame:
    # (high, low, close). Hand true ranges:
    # 0: h-l = 2 (no previous close)
    # 1: max(2, |11-9|=2, |9-9|=0) = 2
    # 2: max(3, |12-10|=2, |9-10|=1) = 3
    # 3: max(2, |14-11|=3, |12-11|=1) = 3   <- gap up: TR exceeds the bar's own range
    # 4: max(3, |13-13|=0, |10-13|=3) = 3
    rows = [(10, 8, 9), (11, 9, 10), (12, 9, 11), (14, 12, 13), (13, 10, 11)]
    return pd.DataFrame(
        {
            "open": [r[2] for r in rows],
            "high": [r[0] for r in rows],
            "low": [r[1] for r in rows],
            "close": [r[2] for r in rows],
            "volume": 1.0,
        },
        index=pd.bdate_range("2024-01-01", periods=len(rows)),
    )


def test_atr_period_three_hand_values_use_gap_aware_true_range() -> None:
    # seed idx2 = (2+2+3)/3 = 7/3; idx3 = (7/3*2+3)/3 = 23/9; idx4 = (23/9*2+3)/3 = 73/27
    result = atr(_atr_frame(), period=3)

    _assert_values(result, [NAN, NAN, 7 / 3, 23 / 9, 73 / 27])


def test_atr_matches_reference_loop() -> None:
    df = _atr_frame()

    result = atr(df, period=2)

    _assert_values(
        result,
        ref_atr(df["high"].tolist(), df["low"].tolist(), df["close"].tolist(), 2),
    )


def test_atr_single_row_is_nan_for_period_two() -> None:
    assert atr(_atr_frame().iloc[:1], period=2).isna().all()


# ---------------------------------------------------------------- VWAP


def _vwap_frame() -> pd.DataFrame:
    # typical prices (h+l+c)/3: 9, 11 | 5 (zero volume), 8
    idx = pd.to_datetime(
        ["2024-03-04 09:30", "2024-03-04 09:31", "2024-03-05 09:30", "2024-03-05 09:31"]
    )
    return pd.DataFrame(
        {
            "open": [9.0, 11.0, 5.0, 8.0],
            "high": [10.0, 12.0, 6.0, 9.0],
            "low": [8.0, 10.0, 4.0, 7.0],
            "close": [9.0, 11.0, 5.0, 8.0],
            "volume": [100.0, 300.0, 0.0, 200.0],
        },
        index=idx,
    )


def test_session_vwap_resets_each_date_and_is_nan_at_zero_volume() -> None:
    # day 1: 9, then (9*100 + 11*300)/400 = 10.5. day 2: NaN while cum volume is 0, then 8.
    result = session_vwap(_vwap_frame())

    _assert_values(result, [9.0, 10.5, NAN, 8.0])


def test_anchored_vwap_accumulates_across_dates_from_anchor() -> None:
    # anchor on 09:31 of day 1: 11; zero-volume bar keeps 11; then (3300 + 8*200)/500 = 9.8
    result = anchored_vwap(_vwap_frame(), pd.Timestamp("2024-03-04 09:31"))

    _assert_values(result, [NAN, 11.0, 11.0, 9.8])


def test_anchored_vwap_anchor_between_bars_starts_at_next_bar() -> None:
    result = anchored_vwap(_vwap_frame(), pd.Timestamp("2024-03-04 09:30:30"))

    _assert_values(result, [NAN, 11.0, 11.0, 9.8])


def test_anchored_vwap_anchor_after_last_bar_is_all_nan() -> None:
    assert anchored_vwap(_vwap_frame(), pd.Timestamp("2025-01-01")).isna().all()


def test_anchored_vwap_does_not_use_bars_before_anchor() -> None:
    df = _vwap_frame()
    altered = df.copy()
    altered.loc[altered.index[0], ["high", "low", "close", "volume"]] = [999.0, 998.0, 997.0, 5e6]

    a = anchored_vwap(df, pd.Timestamp("2024-03-04 09:31"))
    b = anchored_vwap(altered, pd.Timestamp("2024-03-04 09:31"))

    assert a.iloc[1:].tolist() == b.iloc[1:].tolist()


# ---------------------------------------------------------------- properties

_SETTINGS = settings(max_examples=40, deadline=None)


@_SETTINGS
@given(df=ohlc_frames())
def test_rsi_property_stays_within_0_and_100(df: pd.DataFrame) -> None:
    values = rsi(df["close"], 14).dropna()

    assert ((values >= 0) & (values <= 100)).all()


@_SETTINGS
@given(df=ohlc_frames())
def test_bollinger_property_lower_le_middle_le_upper(df: pd.DataFrame) -> None:
    b = bollinger(df["close"]).dropna()

    assert (b["lower"] <= b["middle"]).all()
    assert (b["middle"] <= b["upper"]).all()


@_SETTINGS
@given(df=ohlc_frames())
def test_atr_property_is_non_negative(df: pd.DataFrame) -> None:
    assert (atr(df, 14).dropna() >= 0).all()


def _all_indicators(frame: pd.DataFrame, upto: int) -> list[np.ndarray]:
    c = frame["close"]
    parts = [sma(c, 10), ema(c, 9), rsi(c), atr(frame), session_vwap(frame)]
    parts += [macd(c)[col] for col in ("macd", "signal", "histogram")]
    parts += [bollinger(c)[col] for col in ("middle", "upper", "lower")]
    parts.append(anchored_vwap(frame, frame.index[0]))
    return [p.to_numpy(dtype=float)[:upto] for p in parts]


@_SETTINGS
@given(df=ohlc_frames(), data=st.data())
def test_indicators_property_future_bar_never_changes_earlier_values(
    df: pd.DataFrame, data: st.DataObject
) -> None:
    k = data.draw(st.integers(min_value=1, max_value=len(df) - 1))
    changed = df.copy()
    for col in ("open", "high", "low", "close", "volume"):
        changed.loc[changed.index[k:], col] = changed[col].iloc[k:] * 1.37 + 3.0

    for before, after in zip(_all_indicators(df, k), _all_indicators(changed, k), strict=True):
        np.testing.assert_array_equal(before, after)


def test_rsi_propagates_nan_instead_of_reading_it_as_no_change() -> None:
    close = pd.Series([100.0 + (i % 3) for i in range(40)])
    close.iloc[20] = np.nan

    out = rsi(close, 14)

    assert not out.iloc[:14].notna().any()
    assert out.iloc[14:20].notna().all()
    assert out.iloc[20:].isna().all()


def test_anchored_vwap_rejects_timezone_aware_anchor() -> None:
    df = _daily([100.0 + i for i in range(10)])

    with pytest.raises(ValueError, match="timezone-aware"):
        anchored_vwap(df, pd.Timestamp("2024-01-03", tz="UTC"))
