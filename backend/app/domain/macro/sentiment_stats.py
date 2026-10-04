"""Statistics on event-study results, plus news-sentiment regime and timeline.

Small-sample rule: no p-value is ever computed on fewer than ``min_n`` observations.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd
from scipy import stats

from app.domain.macro.event_study import EventResult

Bucket = Literal["positive", "negative", "neutral"]
Reliability = Literal["clear_effect", "possible_effect", "no_clear_effect"]
RegimeLabel = Literal["more_positive_than_usual", "more_negative_than_usual", "typical"]

BUCKETS: tuple[Bucket, ...] = ("positive", "neutral", "negative")
MIN_BLOCKS = 8  # non-overlapping 30-day baseline blocks needed for the regime z-score
POSITIVE_ABOVE = 0.3
CLEAR_EFFECT_BELOW = 0.05
POSSIBLE_EFFECT_BELOW = 0.2
MIN_DISTINCT = 2  # rank correlation needs variation in both inputs
MIN_SPREAD = 1e-12  # float noise on constant series is ~1e-17


def bucket_of(score: float) -> Bucket:
    """Positive above 0.3, negative below -0.3, otherwise neutral."""
    if score > POSITIVE_ABOVE:
        return "positive"
    if score < -POSITIVE_ABOVE:
        return "negative"
    return "neutral"


def reliability_label(p: float) -> Reliability:
    """Plain-language reliability of a p-value."""
    if p < CLEAR_EFFECT_BELOW:
        return "clear_effect"
    if p < POSSIBLE_EFFECT_BELOW:
        return "possible_effect"
    return "no_clear_effect"


@dataclass(frozen=True)
class Correlation:
    """Spearman rank correlation of sentiment with car_0_1 over ``n`` events."""

    rho: float
    p_value: float
    n: int
    label: Reliability


@dataclass(frozen=True)
class BucketStats:
    """CAR summary for one sentiment bucket. ``n`` counts events; means are None when empty."""

    bucket: Bucket
    n: int
    mean_car_0_1: float | None
    median_car_0_1: float | None
    n_car_0_5: int
    mean_car_0_5: float | None
    median_car_0_5: float | None
    mean_car_pre_5: float | None
    n_car_pre_5: int  # events with a pre-event window; the caveat on the mean rests on these
    # One-sample t-test of car_0_1 against zero; None below min_n or with no spread.
    t: float | None = None
    p_value: float | None = None
    label: Reliability | None = None


@dataclass(frozen=True)
class Difference:
    """Welch t-test of positive versus negative car_0_1 (``mean_diff`` = positive - negative)."""

    mean_diff: float
    t: float
    p_value: float
    label: Reliability
    n_pos: int
    n_neg: int


@dataclass(frozen=True)
class MacroStats:
    """All statistics for one scope (all events, or excluding near-earnings events).

    ``first_event``/``last_event`` are the earliest and latest event dates among the ``n_used``
    events the scope used; both are None exactly when ``n_used == 0``.
    """

    exclude_near_earnings: bool
    min_n: int
    n_used: int
    first_event: date | None
    last_event: date | None
    correlation: Correlation | None
    buckets: dict[Bucket, BucketStats]
    difference: Difference | None


def _mean(values: Sequence[float]) -> float | None:
    return float(np.mean(values)) if values else None


def _median(values: Sequence[float]) -> float | None:
    return float(np.median(values)) if values else None


def _bucket_test(car01: Sequence[float], min_n: int) -> tuple[float, float] | None:
    """One-sample t-test against zero; each bucket claim needs its own evidence."""
    if len(car01) < min_n or len(car01) < MIN_DISTINCT or np.ptp(car01) == 0:
        return None
    res = stats.ttest_1samp(car01, 0.0)
    t, p = float(res.statistic), float(res.pvalue)
    if math.isnan(t) or math.isnan(p):
        return None
    return t, p


def _bucket_stats(bucket: Bucket, events: Sequence[EventResult], min_n: int) -> BucketStats:
    car01 = [e.car_0_1 for e in events if e.car_0_1 is not None]
    car05 = [e.car_0_5 for e in events if e.car_0_5 is not None]
    pre = [e.car_pre_5 for e in events if e.car_pre_5 is not None]
    test = _bucket_test(car01, min_n)
    return BucketStats(
        bucket=bucket,
        n=len(events),
        mean_car_0_1=_mean(car01),
        median_car_0_1=_median(car01),
        n_car_0_5=len(car05),
        mean_car_0_5=_mean(car05),
        median_car_0_5=_median(car05),
        mean_car_pre_5=_mean(pre),
        n_car_pre_5=len(pre),
        t=None if test is None else test[0],
        p_value=None if test is None else test[1],
        label=None if test is None else reliability_label(test[1]),
    )


def _correlation(sent: list[float], car: list[float], min_n: int) -> Correlation | None:
    if len(sent) < min_n or len(set(sent)) < MIN_DISTINCT or len(set(car)) < MIN_DISTINCT:
        return None
    res = stats.spearmanr(sent, car)
    rho, p = float(res.statistic), float(res.pvalue)
    return Correlation(rho=rho, p_value=p, n=len(sent), label=reliability_label(p))


def _difference(pos: list[float], neg: list[float], min_n: int) -> Difference | None:
    if len(pos) < min_n or len(neg) < min_n:
        return None
    if np.ptp(pos) == 0 and np.ptp(neg) == 0:  # no spread in either group: t is undefined
        return None
    res = stats.ttest_ind(pos, neg, equal_var=False)
    t, p = float(res.statistic), float(res.pvalue)
    if math.isnan(t) or math.isnan(p):
        return None
    return Difference(
        mean_diff=float(np.mean(pos) - np.mean(neg)),
        t=t,
        p_value=p,
        label=reliability_label(p),
        n_pos=len(pos),
        n_neg=len(neg),
    )


def compute_stats(
    events: Sequence[EventResult], *, exclude_near_earnings: bool, min_n: int = 10
) -> MacroStats:
    """Correlation, per-bucket CARs and a positive-vs-negative test over usable events.

    Usable means status ok with a car_0_1; near-earnings events are dropped when
    ``exclude_near_earnings`` is set. Tests return None below ``min_n`` samples.
    """
    used = [
        e
        for e in events
        if e.status == "ok"
        and e.car_0_1 is not None
        and not (exclude_near_earnings and e.near_earnings)
    ]
    # Built once so sentiment and CAR can never misalign (``used`` all have a car_0_1).
    pairs = [(e.sentiment, e.car_0_1) for e in used if e.car_0_1 is not None]
    grouped: dict[Bucket, list[EventResult]] = {b: [] for b in BUCKETS}
    for e in used:
        grouped[bucket_of(e.sentiment)].append(e)

    def car01(bucket: Bucket) -> list[float]:
        return [e.car_0_1 for e in grouped[bucket] if e.car_0_1 is not None]

    return MacroStats(
        exclude_near_earnings=exclude_near_earnings,
        min_n=min_n,
        n_used=len(used),
        first_event=min((e.date for e in used), default=None),
        last_event=max((e.date for e in used), default=None),
        correlation=_correlation([s for s, _ in pairs], [c for _, c in pairs], min_n),
        buckets={b: _bucket_stats(b, grouped[b], min_n) for b in BUCKETS},
        difference=_difference(car01("positive"), car01("negative"), min_n),
    )


@dataclass(frozen=True)
class Regime:
    """Recent article-weighted sentiment against the stock's own 30-day-block history."""

    recent_mean: float
    baseline_mean: float
    z: float
    recent_articles: int
    label: RegimeLabel


@dataclass(frozen=True)
class TimelinePoint:
    """Article-weighted sentiment for the week ending Friday ``week_end``."""

    week_end: date
    mean_score: float
    article_count: int


def _weekly(daily_sent: pd.DataFrame) -> pd.DataFrame:
    """Weekly (W-FRI) article-weighted mean score and article count; empty weeks dropped."""
    weighted = daily_sent["mean_score"] * daily_sent["article_count"]
    wsum = weighted.resample("W-FRI").sum()
    count = daily_sent["article_count"].resample("W-FRI").sum()
    out = pd.DataFrame({"mean_score": wsum / count.where(count > 0), "article_count": count})
    return out[out["article_count"] > 0]


def _window_mean(frame: pd.DataFrame) -> float | None:
    """Article-weighted mean score of ``frame``; None without articles."""
    articles = int(frame["article_count"].sum())
    if articles == 0:
        return None
    return float((frame["mean_score"] * frame["article_count"]).sum() / articles)


def sentiment_regime(daily_sent: pd.DataFrame, as_of: date, recent_days: int = 30) -> Regime | None:
    """z-score of recent sentiment against the stock's own 30-day history; None if unavailable.

    Recent = article-weighted mean over (as_of - recent_days, as_of]. The baseline is the
    article-weighted means of the non-overlapping ``recent_days`` blocks before that window,
    stepping back from ``as_of - recent_days``; blocks without news are skipped and at least
    ``MIN_BLOCKS`` are needed. Comparing like with like matters: a 30-day mean is much
    smoother than a weekly one, so a z-score against weekly spread would label far too few
    periods as unusual. Only sessions up to ``as_of`` are used (no look-ahead).
    """
    end = pd.Timestamp(as_of)
    hist = daily_sent.loc[daily_sent.index <= end]
    if hist.empty:
        return None
    age = (end - pd.DatetimeIndex(hist.index)).days.to_numpy()
    block = age // recent_days  # 0 = recent window, 1 = the 30 days before it, ...
    recent = hist.loc[block == 0]
    recent_mean = _window_mean(recent)
    if recent_mean is None:
        return None
    block_means: list[float] = []
    for k in sorted({int(b) for b in block if b > 0}):
        mean = _window_mean(hist.loc[block == k])
        if mean is not None:
            block_means.append(mean)
    if len(block_means) < MIN_BLOCKS:
        return None
    baseline = float(np.mean(block_means))
    spread = float(np.std(block_means, ddof=1))
    if not spread > MIN_SPREAD:  # (near-)zero or NaN: z is undefined
        return None
    z = (recent_mean - baseline) / spread
    label: RegimeLabel = "typical"
    if z >= 1:
        label = "more_positive_than_usual"
    elif z <= -1:
        label = "more_negative_than_usual"
    return Regime(
        recent_mean=recent_mean,
        baseline_mean=baseline,
        z=z,
        recent_articles=int(recent["article_count"].sum()),
        label=label,
    )


def weekly_timeline(daily_sent: pd.DataFrame) -> list[TimelinePoint]:
    """Weekly article-weighted sentiment, oldest first; weeks without news are omitted."""
    if daily_sent.empty:
        return []
    weekly = _weekly(daily_sent)
    return [
        TimelinePoint(week_end=ts.date(), mean_score=float(score), article_count=int(count))
        for ts, score, count in zip(
            pd.DatetimeIndex(weekly.index),
            weekly["mean_score"].tolist(),
            weekly["article_count"].tolist(),
            strict=True,
        )
    ]
