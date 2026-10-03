"""Response models for the analysis endpoints.

Explicit pydantic classes (rather than the domain dataclasses) so the OpenAPI schema is precise
for the frontend's generated types. Field names are snake_case throughout.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.services.status import DataStatus

Lean = Literal["bullish", "bearish", "neutral"]
Bias = Literal["bullish", "bearish", "neutral"]
Reliability = Literal["likely_real", "weak_evidence", "could_be_chance"]
Bucket = Literal["positive", "negative", "neutral"]


class PriceStatuses(BaseModel):
    prices: DataStatus
    overall: DataStatus


class FullStatuses(BaseModel):
    prices: DataStatus
    events: DataStatus
    news: DataStatus
    overall: DataStatus


# --- technical -----------------------------------------------------------------------------


class SignalOut(BaseModel):
    key: str
    label: str
    direction: Literal[-1, 0, 1]
    weight: float
    detail: str


class ExpectedRange(BaseModel):
    low: float
    high: float


class OutlookOut(BaseModel):
    lean: Lean
    score: float
    signals: list[SignalOut]
    expected_range: ExpectedRange | None
    expected_range_coverage: float  # share of past weeks that fell inside expected_range
    last_close: float
    as_of: date


class PatternStatsOut(BaseModel):
    n: int
    up_count: int
    hit_rate: float | None
    base_rate: float | None
    edge: float | None
    base_down_rate: float | None
    base_n: int
    sufficient: bool
    label: str  # plain-English reliability sentence
    bias: Bias


class RecentPattern(BaseModel):
    key: str
    label: str
    bias: Bias
    date: date
    stats: PatternStatsOut | None


class TechnicalReport(BaseModel):
    symbol: str
    outlook: OutlookOut
    recent_patterns: list[RecentPattern]
    data_status: PriceStatuses


# --- macro ---------------------------------------------------------------------------------


class HeadlineOut(BaseModel):
    title: str
    url: str
    source: str


class TopEventOut(BaseModel):
    date: date
    sentiment: float
    article_count: int
    car_0_1: float
    car_0_5: float | None
    near_earnings: bool
    headlines: list[HeadlineOut]


class FindingOut(BaseModel):
    text: str
    based_on_events: int
    reliability: Reliability | None
    p_value: float | None


class CorrelationOut(BaseModel):
    rho: float
    p_value: float
    n: int
    label: Reliability


class BucketStatsOut(BaseModel):
    bucket: Bucket
    n: int
    mean_car_0_1: float | None
    median_car_0_1: float | None
    n_car_0_5: int
    mean_car_0_5: float | None
    median_car_0_5: float | None
    mean_car_pre_5: float | None
    t: float | None
    p_value: float | None
    label: Reliability | None


class DifferenceOut(BaseModel):
    mean_diff: float
    t: float
    p_value: float
    label: Reliability
    n_pos: int
    n_neg: int


class MacroStatsOut(BaseModel):
    exclude_near_earnings: bool
    min_n: int
    n_used: int
    correlation: CorrelationOut | None
    buckets: dict[Bucket, BucketStatsOut]
    difference: DifferenceOut | None


class RegimeOut(BaseModel):
    recent_mean: float
    baseline_mean: float
    z: float
    recent_articles: int
    label: Literal["more_positive_than_usual", "more_negative_than_usual", "typical"]


class TimelinePointOut(BaseModel):
    week_end: date
    mean_score: float
    article_count: int


class MacroReportOut(BaseModel):
    top_events: list[TopEventOut]
    headline_findings: list[FindingOut]
    primary_findings: list[FindingOut]
    secondary_findings: list[FindingOut]
    stats_all: MacroStatsOut
    stats_ex_earnings: MacroStatsOut
    regime: RegimeOut | None
    timeline: list[TimelinePointOut]
    events_total: int
    events_insufficient: int


class IngestionOut(BaseModel):
    months_done: int
    months_total: int
    in_progress: bool


class MacroResponse(BaseModel):
    symbol: str
    name: str
    report: MacroReportOut | None  # None until there is price history to analyse
    ingestion: IngestionOut
    data_status: FullStatuses


# --- chart ---------------------------------------------------------------------------------


class SeriesPoint(BaseModel):
    time: str | int  # "YYYY-MM-DD" for daily bars, UNIX epoch seconds (UTC) for hourly bars
    value: float


class Candle(BaseModel):
    time: str | int
    open: float
    high: float
    low: float
    close: float
    volume: float


class Marker(BaseModel):
    time: str | int
    kind: Literal["earnings", "dividend", "split", "pattern", "news"]
    label: str
    bias: Bias | None = None
    pattern: str | None = None
    car_0_1: float | None = None  # news markers only: abnormal return over 2 sessions, fraction


class ChartData(BaseModel):
    symbol: str
    range: Literal["1W", "1M", "6M", "1Y", "2Y"]
    interval: Literal["1d", "1h"]
    candles: list[Candle]
    indicators: dict[str, list[SeriesPoint]]
    markers: list[Marker]
    data_status: FullStatuses
