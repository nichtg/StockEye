"""Market-adjusted event study of news sentiment.

Guards against four classic errors:

* look-ahead: the market model for an event at position t uses only positions <= t - 20,
  and nothing after an event is ever used to judge an earlier one;
* overlapping windows: events are thinned so no two are within ``exclusion`` sessions;
* confounding: events within five sessions of an earnings date are flagged so the statistics
  can exclude them;
* contaminated baselines: estimation windows skip the post-event windows of selected events
  and the sessions around earnings announcements.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np
import numpy.typing as npt
import pandas as pd

EventStatus = Literal["ok", "insufficient_estimation"]

# Length of the post-event window [0, +5] that is kept out of estimation windows.
POST_WINDOW = 5
# An event is flagged near earnings when an earnings session is within this many positions.
EARNINGS_NEAR = 5
# Earnings sessions [e-1, e+1] are masked out of estimation windows.
EARNINGS_MASK = 1

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class EventResult:
    """Abnormal-return outcome for one news event (returns are simple fractions, 0.01 = 1%)."""

    date: date
    sentiment: float
    article_count: int
    alpha: float | None
    beta: float | None
    car_0_0: float | None
    car_0_1: float | None
    car_0_5: float | None
    car_pre_5: float | None
    near_earnings: bool
    status: EventStatus


def select_events(
    daily_sent: pd.DataFrame, trading_index: pd.DatetimeIndex, exclusion: int = 5
) -> list[pd.Timestamp]:
    """Pick non-overlapping event sessions causally, returned sorted by date.

    Salience is ``|mean_score| * log1p(article_count)``. Sessions are walked in date order
    using bounded-horizon windows:

    1. When a news session at trading position ``p`` arrives with
       ``p > last_selected + exclusion``, a candidate window covering positions
       ``[p, p + exclusion]`` opens.
    2. The most salient session in that window is selected (ties go to the earliest).
    3. ``last_selected`` becomes the chosen position and the walk resumes after
       ``last_selected + exclusion``.

    Selected [0, +5] windows therefore stay disjoint. A global greedy rule ("take the most
    salient session anywhere, then block its neighbours") was wrong because a salient news
    day arriving *later* could displace an event chosen earlier, so earlier results would
    change as history grew, which is look-ahead. Here a window closes ``exclusion`` sessions
    after it opens, so only the final, still-open window (which contains ``as_of``) can be
    altered by future news. Heavily covered stocks have news almost every day, so per-day
    windows would otherwise overlap and the same price move would be counted many times.
    Sessions that are not in ``trading_index`` cannot be evaluated and are ignored.
    """
    if daily_sent.empty:
        return []
    raw = trading_index.get_indexer(pd.DatetimeIndex(daily_sent.index))
    salience_all = np.abs(daily_sent["mean_score"].to_numpy(dtype=float)) * np.log1p(
        daily_sent["article_count"].to_numpy(dtype=float)
    )
    rows = sorted((int(raw[i]), float(salience_all[i]), i) for i in range(len(raw)) if raw[i] >= 0)
    picked: list[int] = []
    last = -exclusion - 1  # sentinel: no earlier event, so position 0 is eligible
    i = 0
    while i < len(rows):
        pos = rows[i][0]
        if pos <= last + exclusion:
            i += 1
            continue
        best = i
        j = i
        while j < len(rows) and rows[j][0] <= pos + exclusion:
            if rows[j][1] > rows[best][1]:  # strict: ties keep the earliest
                best = j
            j += 1
        picked.append(rows[best][2])
        last = rows[best][0]
        i = j
    picked.sort()
    return [pd.Timestamp(daily_sent.index[k]) for k in picked]


def _car(ar: FloatArray, t: int, start: int, end: int) -> float | None:
    """Sum of abnormal returns over positions [t+start, t+end]; None if any is unavailable."""
    lo, hi = t + start, t + end
    if lo < 1 or hi >= len(ar):  # position 0 has no return
        return None
    window = ar[lo : hi + 1]
    if not np.all(np.isfinite(window)):
        return None
    return float(window.sum())


def _fit_market_model(
    r_s: FloatArray,
    r_m: FloatArray,
    excluded: npt.NDArray[np.bool_],
    t: int,
    *,
    est_window: tuple[int, int],
    min_obs: int,
) -> tuple[float, float] | None:
    """OLS alpha, beta over positions [t-start, t-end] (inclusive), skipping event windows."""
    lo = max(t - est_window[0], 1)
    hi = t - est_window[1]
    if hi < lo:
        return None
    y = r_s[lo : hi + 1]
    x = r_m[lo : hi + 1]
    keep = np.isfinite(y) & np.isfinite(x) & ~excluded[lo : hi + 1]
    if int(keep.sum()) < min_obs:
        return None
    y, x = y[keep], x[keep]
    x_dev = x - x.mean()
    var = float(np.dot(x_dev, x_dev))
    if var <= 0.0:
        return None
    beta = float(np.dot(x_dev, y - y.mean()) / var)
    alpha = float(y.mean() - beta * x.mean())
    return alpha, beta


def _earnings_positions(earnings_dates: Sequence[date], index: pd.DatetimeIndex) -> list[int]:
    """Each earnings date maps to the session on or after it; dates past the data are dropped."""
    out: list[int] = []
    for d in earnings_dates:
        pos = int(index.searchsorted(pd.Timestamp(d), side="left"))
        if pos < len(index):
            out.append(pos)
    return out


def run_event_study(
    stock_close: pd.Series,
    bench_close: pd.Series,
    daily_sent: pd.DataFrame,
    earnings_dates: Sequence[date],
    *,
    exclusion: int = 5,
    est_window: tuple[int, int] = (150, 20),
    min_est_obs: int = 60,
) -> list[EventResult]:
    """Run the event study; one ``EventResult`` per selected event, sorted by date.

    ``stock_close`` and ``bench_close`` are daily closes on naive date indexes and are
    inner-joined. ``est_window=(150, 20)`` means positions [t-150, t-20]. Events with fewer
    than ``min_est_obs`` usable estimation observations are returned with status
    ``insufficient_estimation`` and no statistics.
    """
    closes = pd.concat([stock_close, bench_close], axis=1, join="inner").dropna()
    closes.columns = pd.Index(["stock", "bench"])
    index = pd.DatetimeIndex(closes.index)
    # Return at position p is the move from close p-1 to close p; position 0 is NaN.
    rets = closes.pct_change()
    r_s = rets["stock"].to_numpy(dtype=float)
    r_m = rets["bench"].to_numpy(dtype=float)

    selected = select_events(daily_sent, index, exclusion)
    sel_pos = [int(p) for p in index.get_indexer(pd.DatetimeIndex(selected))]
    scores = dict(zip(daily_sent.index, daily_sent["mean_score"].tolist(), strict=True))
    counts = dict(zip(daily_sent.index, daily_sent["article_count"].tolist(), strict=True))

    excluded = np.zeros(len(index), dtype=bool)
    for p in sel_pos:
        excluded[p : p + POST_WINDOW + 1] = True
    earn_pos = _earnings_positions(earnings_dates, index)
    for e in earn_pos:
        excluded[max(0, e - EARNINGS_MASK) : e + EARNINGS_MASK + 1] = True

    results: list[EventResult] = []
    for ts, t in zip(selected, sel_pos, strict=True):
        near = any(abs(e - t) <= EARNINGS_NEAR for e in earn_pos)
        fit = _fit_market_model(r_s, r_m, excluded, t, est_window=est_window, min_obs=min_est_obs)
        if fit is None:
            alpha = beta = car_00 = car_01 = car_05 = car_pre = None
        else:
            alpha, beta = fit
            ar = r_s - (alpha + beta * r_m)
            car_00 = _car(ar, t, 0, 0)
            car_01 = _car(ar, t, 0, 1)
            car_05 = _car(ar, t, 0, 5)
            car_pre = _car(ar, t, -5, -1)
        results.append(
            EventResult(
                date=ts.date(),
                sentiment=float(scores[ts]),
                article_count=int(counts[ts]),
                alpha=alpha,
                beta=beta,
                car_0_0=car_00,
                car_0_1=car_01,
                car_0_5=car_05,
                car_pre_5=car_pre,
                near_earnings=near,
                status="insufficient_estimation" if fit is None else "ok",
            )
        )
    return results
