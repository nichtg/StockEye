# ruff: noqa: DTZ001
"""Input validation shared by every function that takes a price frame."""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest
from technical_refs import frame

from app.domain.technical import (
    PATTERNS,
    PatternHit,
    PatternKey,
    anchored_vwap,
    atr,
    build_outlook,
    detect_patterns,
    pattern_reliability,
    session_vwap,
)

AS_OF = datetime(2024, 3, 1)


def _daily(closes: list[float]) -> pd.DataFrame:
    return frame([(c, c + 1.0, c - 1.0, c) for c in closes])


def _doji_hit(df: pd.DataFrame, index: int) -> PatternHit:
    key = PatternKey.DOJI
    return PatternHit(key, PATTERNS[key].bias, index, df.index[index].to_pydatetime())


def _with_nan(column: str = "close", at: int = 12) -> pd.DataFrame:
    df = _daily([100.0 + i for i in range(40)])
    df.iloc[at, df.columns.get_loc(column)] = np.nan  # type: ignore[index]
    return df


@pytest.mark.parametrize("column", ["open", "high", "low", "close"])
def test_functions_taking_a_frame_reject_nan_prices_naming_the_date(column: str) -> None:
    df = _with_nan(column)
    stamp = str(df.index[12])
    hit = _doji_hit(df, 1)

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
