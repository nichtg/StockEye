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
Reliability = Literal["likely_real", "weak_evidence", "could_be_chance"]
RegimeLabel = Literal["more_positive_than_usual", "more_negative_than_usual", "typical"]

BUCKETS: tuple[Bucket, ...] = ("positive", "neutral", "negative")
MIN_WEEKS = 12
POSITIVE_ABOVE = 0.3
LIKELY_REAL_BELOW = 0.05
WEAK_EVIDENCE_BELOW = 0.2
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
    if p < LIKELY_REAL_BELOW:
        return "likely_real"
    if p < WEAK_EVIDENCE_BELOW:
        return "weak_evidence"
    return "could_be_chance"


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
    """All statistics for one scope (all events, or excluding near-earnings events)."""

    exclude_near_earnings: bool
    min_n: int
    n_used: int
    correlation: Correlation | None
    buckets: dict[Bucket, BucketStats]
    difference: Difference | None


def _mean(values: Sequence[float]) -> float | None:
    return float(np.mean(values)) if values else None


def _median(values: Sequence[float]) -> float | None:
    return float(np.median(values)) if values else None


def _bucket_stats(bucket: Bucket, events: Sequence[EventResult]) -> BucketStats:
    car01 = [e.car_0_1 for e in events if e.car_0_1 is not None]
    car05 = [e.car_0_5 for e in events if e.car_0_5 is not None]
    pre = [e.car_pre_5 for e in events if e.car_pre_5 is not None]
    return BucketStats(
        bucket=bucket,
        n=len(events),
        mean_car_0_1=_mean(car01),
        median_car_0_1=_median(car01),
        n_car_0_5=len(car05),
        mean_car_0_5=_mean(car05),
        median_car_0_5=_median(car05),
        mean_car_pre_5=_mean(pre),
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
    grouped: dict[Bucket, list[EventResult]] = {b: [] for b in BUCKETS}
    for e in used:
        grouped[bucket_of(e.sentiment)].append(e)

    def car01(bucket: Bucket) -> list[float]:
        return [e.car_0_1 for e in grouped[bucket] if e.car_0_1 is not None]

    return MacroStats(
        exclude_near_earnings=exclude_near_earnings,
        min_n=min_n,
        n_used=len(used),
        correlation=_correlation(
            [e.sentiment for e in used], [e.car_0_1 for e in used if e.car_0_1 is not None], min_n
        ),
        buckets={b: _bucket_stats(b, grouped[b]) for b in BUCKETS},
        difference=_difference(car01("positive"), car01("negative"), min_n),
    )


@dataclass(frozen=True)
class Regime:
    """Recent article-weighted sentiment against the stock's own weekly history."""

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


def sentiment_regime(daily_sent: pd.DataFrame, as_of: date, recent_days: int = 30) -> Regime | None:
    """z-score of recent sentiment against weekly history; None without enough data.

    Only sessions up to ``as_of`` are used (no look-ahead). Needs at least 12 weekly points,
    some news in (as_of - recent_days, as_of], and a non-degenerate weekly spread.
    """
    end = pd.Timestamp(as_of)
    hist = daily_sent.loc[daily_sent.index <= end]
    if hist.empty:
        return None
    weekly = _weekly(hist)
    if len(weekly) < MIN_WEEKS:
        return None
    recent = hist.loc[hist.index > end - pd.Timedelta(days=recent_days)]
    recent_articles = int(recent["article_count"].sum())
    if recent_articles == 0:
        return None
    recent_mean = float((recent["mean_score"] * recent["article_count"]).sum() / recent_articles)
    baseline = float(weekly["mean_score"].mean())
    spread = float(weekly["mean_score"].std(ddof=1))
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
        recent_articles=recent_articles,
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
