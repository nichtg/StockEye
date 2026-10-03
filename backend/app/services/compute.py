"""CPU-bound assembly of reports from prepared inputs. Synchronous: callers use ``to_thread``."""

from dataclasses import asdict
from datetime import date
from typing import Literal, cast

import pandas as pd

from app.domain.macro import (
    ScoredArticle,
    SessionCalendar,
    build_macro_report,
    compute_stats,
    daily_sentiment,
    run_event_study,
    sentiment_regime,
    weekly_timeline,
)
from app.domain.technical import (
    PATTERNS,
    PatternStats,
    anchored_vwap,
    build_outlook,
    detect_patterns,
    pattern_reliability,
    trend_context,
)
from app.providers.models import CorporateEvent
from app.services import charts
from app.services.calendars import exchange_tz
from app.services.charts import RANGES, RangeKey
from app.services.reports import (
    Bias,
    ChartData,
    ExpectedRange,
    FullStatuses,
    MacroReportOut,
    OutlookOut,
    PatternStatsOut,
    PriceStatuses,
    RecentPattern,
    SignalOut,
    TechnicalReport,
)
from app.services.status import ok

RECENT_SESSIONS = 3
VWAP_ANCHOR_BACK = 5  # anchored at the 5th-last session


def build_chart(
    symbol: str,
    range_key: RangeKey,
    indicators: list[str],
    *,
    frame: pd.DataFrame,
    events: list[CorporateEvent],
    news: list[tuple[date, str, float]],
) -> ChartData:
    """Chart payload with placeholder statuses; the service overwrites them afterwards."""
    interval, _ = RANGES[range_key]
    tz = exchange_tz(symbol)
    mask = charts.visible_mask(frame, range_key)
    hits = detect_patterns(frame) if interval == "1d" else []
    placeholder = ok()
    return ChartData(
        symbol=symbol,
        range=range_key,
        interval=interval,
        candles=charts.candles(frame, mask, interval, tz),
        indicators=charts.indicator_series(frame, mask, indicators, interval, tz),
        markers=charts.build_markers(
            frame, mask, interval, tz, events=events, hits=hits, news=news
        ),
        data_status=FullStatuses(
            prices=placeholder, events=placeholder, news=placeholder, overall=placeholder
        ),
    )


def _stats_label(stats: PatternStats, bias: str) -> str:
    if stats.n == 0:
        return "This pattern has no completed past occurrences to learn from."
    if stats.hit_rate is None or stats.base_rate is None:
        return f"Seen {stats.n} times; it makes no directional prediction."
    verb = "rose" if bias == "bullish" else "fell"
    text = (
        f"Seen {stats.n} times in this stock's history; the price {verb} within a week "
        f"{stats.success_count} times ({stats.hit_rate:.0%}) versus {stats.base_rate:.0%} on a "
        "typical day."
    )
    return text if stats.sufficient else f"{text} That is too few cases to rely on."


def compute_technical(symbol: str, frame: pd.DataFrame, statuses: PriceStatuses) -> TechnicalReport:
    """Outlook plus the last three sessions' patterns, each with its historical reliability."""
    hits = detect_patterns(frame)
    reliability = pattern_reliability(frame, hits, trend=trend_context(frame))
    last = len(frame) - 1
    recent = [h for h in hits if h.index > last - RECENT_SESSIONS]
    anchor = frame.index[max(0, len(frame) - VWAP_ANCHOR_BACK)]
    vwap = float(anchored_vwap(frame, anchor).iloc[-1])
    as_of = pd.Timestamp(frame.index[-1]).to_pydatetime()
    outlook = build_outlook(frame, recent, reliability, None if pd.isna(vwap) else vwap, as_of)
    patterns: list[RecentPattern] = []
    for hit in sorted(recent, key=lambda h: h.index, reverse=True):
        stats = reliability.get(hit.key)
        bias: Bias = hit.bias.value
        patterns.append(
            RecentPattern(
                key=hit.key.value,
                label=PATTERNS[hit.key].label,
                bias=bias,
                date=pd.Timestamp(hit.date).date(),
                stats=None
                if stats is None
                else PatternStatsOut(
                    n=stats.n,
                    up_count=stats.up_count,
                    hit_rate=stats.hit_rate,
                    base_rate=stats.base_rate,
                    edge=stats.edge,
                    base_down_rate=stats.base_down_rate,
                    base_n=stats.base_n,
                    sufficient=stats.sufficient,
                    label=_stats_label(stats, bias),
                    bias=bias,
                ),
            )
        )
    expected = outlook.expected_range
    return TechnicalReport(
        symbol=symbol,
        outlook=OutlookOut(
            lean=outlook.lean,
            score=outlook.score,
            signals=[
                SignalOut(
                    key=s.key,
                    label=s.label,
                    direction=cast(Literal[-1, 0, 1], s.direction),
                    weight=s.weight,
                    detail=s.detail,
                )
                for s in outlook.signals
            ],
            expected_range=None
            if expected is None
            else ExpectedRange(low=expected[0], high=expected[1]),
            expected_range_coverage=outlook.expected_range_coverage,
            last_close=outlook.last_close,
            as_of=as_of.date(),
        ),
        recent_patterns=patterns,
        data_status=statuses,
    )


def compute_macro(
    stock: pd.DataFrame,
    bench: pd.DataFrame,
    articles: list[ScoredArticle],
    earnings: list[date],
    cal: SessionCalendar,
) -> MacroReportOut:
    """News-sentiment event study: sentiment per session, abnormal returns, then statistics."""
    daily_sent, by_session = daily_sentiment(articles, cal)
    events = run_event_study(stock["close"], bench["close"], daily_sent, earnings)
    stats_all = compute_stats(events, exclude_near_earnings=False)
    stats_ex = compute_stats(events, exclude_near_earnings=True)
    regime = sentiment_regime(daily_sent, pd.Timestamp(stock.index[-1]).date())
    timeline = weekly_timeline(daily_sent)
    report = build_macro_report(events, stats_all, stats_ex, regime, timeline, by_session)
    return MacroReportOut.model_validate(asdict(report))
