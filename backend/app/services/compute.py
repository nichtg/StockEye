"""CPU-bound assembly of reports from prepared inputs. Synchronous: callers use ``to_thread``."""

from dataclasses import asdict
from datetime import date

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
    PatternHit,
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
from app.services.charts import RANGES
from app.services.reports import (
    ChartData,
    FullStatuses,
    LatestPatternOut,
    MacroReportOut,
    OutlookOut,
    PriceStatuses,
    RangeKey,
    RecentPattern,
    TechnicalReport,
)

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
    statuses: FullStatuses,
) -> ChartData:
    """Chart payload: candles, the requested indicator lines and the markers on visible bars."""
    interval, _ = RANGES[range_key]
    tz = exchange_tz(symbol)
    mask = charts.visible_mask(frame, range_key)
    hits = detect_patterns(frame) if interval == "1d" else []
    return ChartData(
        symbol=symbol,
        range=range_key,
        interval=interval,
        candles=charts.candles(frame, mask, interval, tz),
        indicators=charts.indicator_series(frame, mask, indicators, interval, tz),
        markers=charts.build_markers(
            frame, mask, interval, tz, events=events, hits=hits, news=news
        ),
        data_status=statuses,
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


def _hit_fields(hit: PatternHit) -> dict[str, object]:
    """Fields shared by ``RecentPattern`` and ``LatestPatternOut`` for one pattern hit."""
    return {
        "label": PATTERNS[hit.key].label,
        "bias": hit.bias.value,
        "date": pd.Timestamp(hit.date).date(),
    }


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
        bias = hit.bias.value
        # The response models are deliberately separate from the domain dataclasses (see
        # ``reports``), so each one is built from plain dicts at this single boundary.
        stats_out = (
            None
            if stats is None
            else {**asdict(stats), "label": _stats_label(stats, bias), "bias": bias}
        )
        patterns.append(
            RecentPattern.model_validate(
                {"key": hit.key.value, **_hit_fields(hit), "stats": stats_out}
            )
        )
    expected = outlook.expected_range
    outlook_out = OutlookOut.model_validate(
        {
            **asdict(outlook),
            "expected_range": expected and {"low": expected[0], "high": expected[1]},
            "as_of": as_of.date(),
        }
    )
    latest = None
    if not recent and hits:
        # ``detect_patterns`` returns hits sorted by index, so the last one is the most recent.
        hit = hits[-1]
        latest = LatestPatternOut.model_validate(
            {"pattern": hit.key.value, **_hit_fields(hit), "sessions_ago": last - hit.index}
        )
    return TechnicalReport(
        symbol=symbol,
        outlook=outlook_out,
        recent_patterns=patterns,
        latest_pattern=latest,
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
