"""Assemble the macro report: top events with headlines and plain-English findings.

Finding text is written for non-statisticians: it never contains the bare letters used as
statistical symbols for sample size or probability. The raw p-value travels in
``Finding.p_value`` so the UI can show it in a "Details" row.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from app.domain.macro.alignment import ScoredArticle
from app.domain.macro.event_study import EventResult
from app.domain.macro.sentiment_stats import (
    BucketStats,
    MacroStats,
    Regime,
    Reliability,
    TimelinePoint,
)

MAX_HEADLINES = 3


@dataclass(frozen=True)
class Headline:
    title: str
    url: str
    source: str


@dataclass(frozen=True)
class TopEvent:
    """A large market-adjusted move after news (returns are fractions, 0.01 = 1%)."""

    date: date
    sentiment: float
    article_count: int
    car_0_1: float
    car_0_5: float | None
    near_earnings: bool
    headlines: list[Headline]


@dataclass(frozen=True)
class Finding:
    """One plain-English sentence. ``based_on_events`` counts events (or articles for regime)."""

    text: str
    based_on_events: int
    reliability: Reliability | None = None
    p_value: float | None = None


@dataclass(frozen=True)
class MacroReport:
    top_events: list[TopEvent]
    headline_findings: list[Finding]
    stats_all: MacroStats
    stats_ex_earnings: MacroStats
    regime: Regime | None
    timeline: list[TimelinePoint]
    events_total: int
    events_insufficient: int


def _pct(x: float) -> str:
    """Signed percentage with one decimal; avoids a negative zero."""
    value = round(x * 100, 1)
    if value == 0:
        value = 0.0
    return f"{value:+.1f}%"


def _pct_abs(x: float) -> str:
    return f"{abs(round(x * 100, 1)):.1f}%"


def _chance_phrase(p: float) -> str:
    in_100 = round(p * 100)
    if in_100 < 1:
        return "fewer than 1 in 100 times"
    return f"about {in_100} in 100 times"


def _reliability_text(label: Reliability, p: float, what: str) -> str:
    """Reliability sentence; ``what`` is e.g. "a gap this large"."""
    chance = _chance_phrase(p)
    if label == "likely_real":
        only = "" if chance.startswith("fewer") else "only "
        return (
            f"Likely a real effect: if news had no influence, {what} would appear "
            f"by chance {only}{chance}."
        )
    if label == "weak_evidence":
        return f"Weak evidence: {what} would appear by chance {chance}."
    return f"Could be chance: {what} would appear by chance {chance}, too often to rule out luck."


def _beat_or_lag(x: float) -> str:
    return "beat" if x >= 0 else "lagged"


def _bucket_finding(label: str, bucket: BucketStats, min_n: int, scope: str) -> Finding:
    if bucket.n < min_n or bucket.mean_car_0_1 is None:
        return Finding(
            text=(
                f"{scope}Not enough {label}-news events yet to judge "
                f"(found {bucket.n}; need at least {min_n})."
            ),
            based_on_events=bucket.n,
        )
    m = bucket.mean_car_0_1
    return Finding(
        text=(
            f"{scope}After {label} news, the stock {_beat_or_lag(m)} the market by "
            f"{_pct_abs(m)} on average over the next 2 days."
        ),
        based_on_events=bucket.n,
    )


def _scope_findings(stats: MacroStats, scope_label: str) -> list[Finding]:
    scope = f"{scope_label}: "
    if stats.n_used < stats.min_n:
        return [
            Finding(
                text=(
                    f"{scope}Not enough news events yet to judge "
                    f"(found {stats.n_used}; need at least {stats.min_n})."
                ),
                based_on_events=stats.n_used,
            )
        ]
    out = [
        _bucket_finding("positive", stats.buckets["positive"], stats.min_n, scope),
        _bucket_finding("negative", stats.buckets["negative"], stats.min_n, scope),
    ]
    diff = stats.difference
    if diff is not None:
        total = diff.n_pos + diff.n_neg
        out.append(
            Finding(
                text=(
                    f"{scope}The gap between positive-news and negative-news reactions was "
                    f"{_pct(diff.mean_diff)} over the next 2 days."
                ),
                based_on_events=total,
            )
        )
        out.append(
            Finding(
                text=_reliability_text(diff.label, diff.p_value, "a gap this large"),
                based_on_events=total,
                reliability=diff.label,
                p_value=diff.p_value,
            )
        )
    corr = stats.correlation
    if corr is not None:
        direction = "better" if corr.rho > 0 else "worse"
        out.append(
            Finding(
                text=(
                    f"{scope}Across {corr.n} news events, more positive sentiment tended to go "
                    f"with {direction} market-adjusted moves (rank correlation {corr.rho:+.2f})."
                ),
                based_on_events=corr.n,
            )
        )
        out.append(
            Finding(
                text=_reliability_text(corr.label, corr.p_value, "a pattern this strong"),
                based_on_events=corr.n,
                reliability=corr.label,
                p_value=corr.p_value,
            )
        )
    return out


def _regime_finding(regime: Regime) -> Finding:
    phrase = {
        "more_positive_than_usual": "more positive than usual",
        "more_negative_than_usual": "more negative than usual",
        "typical": "about typical",
    }[regime.label]
    return Finding(
        text=(
            f"Recent news for this stock has been {phrase} "
            f"(based on {regime.recent_articles} articles)."
        ),
        based_on_events=regime.recent_articles,
    )


def _top_events(
    events: Sequence[EventResult],
    session_articles: Mapping[date, Sequence[ScoredArticle]],
    top_n: int,
) -> list[TopEvent]:
    usable = [e for e in events if e.status == "ok" and e.car_0_1 is not None]
    usable.sort(key=lambda e: (-abs(e.car_0_1 or 0.0), e.date))
    out: list[TopEvent] = []
    for e in usable[:top_n]:
        # Most extreme-scoring stories first: they most plausibly drove the sentiment reading.
        arts = sorted(
            session_articles.get(e.date, ()),
            key=lambda a: (-abs(a.score), a.published_at),
        )[:MAX_HEADLINES]
        out.append(
            TopEvent(
                date=e.date,
                sentiment=e.sentiment,
                article_count=e.article_count,
                car_0_1=e.car_0_1 or 0.0,
                car_0_5=e.car_0_5,
                near_earnings=e.near_earnings,
                headlines=[Headline(a.title, a.url, a.source) for a in arts],
            )
        )
    return out


def build_macro_report(  # noqa: PLR0917 - signature fixed by the service contract
    events: Sequence[EventResult],
    stats_all: MacroStats,
    stats_ex_earnings: MacroStats,
    regime: Regime | None,
    timeline: Sequence[TimelinePoint],
    session_articles: Mapping[date, Sequence[ScoredArticle]],
    *,
    top_n: int = 10,
) -> MacroReport:
    """Combine events, statistics and context into the report shown to the user.

    Findings lead with the earnings-excluded scope (cleaner, not confounded by results
    announcements), then the all-events scope, then the recent-sentiment regime.
    """
    findings = _scope_findings(stats_ex_earnings, "Excluding earnings periods")
    findings += _scope_findings(stats_all, "Including earnings periods")
    if regime is not None:
        findings.append(_regime_finding(regime))
    return MacroReport(
        top_events=_top_events(events, session_articles, top_n),
        headline_findings=findings,
        stats_all=stats_all,
        stats_ex_earnings=stats_ex_earnings,
        regime=regime,
        timeline=list(timeline),
        events_total=len(events),
        events_insufficient=sum(1 for e in events if e.status != "ok"),
    )
