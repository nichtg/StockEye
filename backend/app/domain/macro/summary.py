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
    Bucket,
    BucketStats,
    MacroStats,
    Regime,
    Reliability,
    TimelinePoint,
    reliability_label,
)

MAX_HEADLINES = 3
MIN_LINK = 0.1  # |rank correlation| below this is described as no clear link
VERY_OFTEN_AT = 95  # "in 100" figure from which chance is described as "very often"
PRE_MOVE_CAVEAT = 0.01  # a mean pre-event move this large (1%) gets a caveat sentence


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
    headline_findings: list[Finding]  # primary + regime, kept for compatibility
    primary_findings: list[Finding]  # shown first: ex-earnings scope (or the only scope)
    secondary_findings: list[Finding]  # all-events scope; the UI shows it under Details
    stats_all: MacroStats
    stats_ex_earnings: MacroStats
    regime: Regime | None
    timeline: list[TimelinePoint]
    events_total: int
    events_insufficient: int


def _pct_abs(x: float) -> str:
    return f"{abs(round(x * 100, 1)):.1f}%"


def _reliability_finding(p: float, what: str, based_on: int, scope: str = "") -> Finding:
    """Reliability sentence; ``what`` is e.g. "a gap this large". The raw p stays in the field.

    The label and the "about X in 100" figure come from the same rounded value, so they can
    never disagree (for example "likely a real effect ... about 5 in 100").
    """
    raw = round(p * 100)
    below_floor = raw < 1
    in_100 = max(1, raw)
    label = reliability_label(in_100 / 100)
    chance = "fewer than 1 in 100 times" if below_floor else f"about {in_100} in 100 times"
    if label == "likely_real":
        only = "" if below_floor else "only "
        text = (
            f"Likely a real effect: if news had no influence, {what} would appear "
            f"by chance {only}{chance}."
        )
    elif label == "weak_evidence":
        text = f"Weak evidence: {what} would appear by chance {chance}."
    elif in_100 >= VERY_OFTEN_AT:
        text = (
            f"Could be chance: {what} would very often appear by chance, "
            "too often to rule out luck."
        )
    else:
        text = (
            f"Could be chance: {what} would appear by chance {chance}, too often to rule out luck."
        )
    return Finding(text=f"{scope}{text}", based_on_events=based_on, reliability=label, p_value=p)


def _reaction_phrase(m: float) -> str:
    """How the stock moved against its market-model expectation, in plain words."""
    rounded = round(m * 100, 1)
    if rounded == 0:
        return "moved in line with what the market predicted"
    side = "better" if rounded > 0 else "worse"
    return f"did {_pct_abs(m)} {side} than its usual relationship with the market would predict"


def _gap_sentence(mean_diff: float) -> str:
    """Positive-versus-negative comparison; a gap that rounds to zero has no direction."""
    rounded = round(mean_diff * 100, 1)
    if rounded == 0:
        return "Positive-news days did about the same as negative-news days."
    side = "better" if rounded > 0 else "worse"
    return f"Positive-news days did {_pct_abs(mean_diff)} {side} than negative-news days."


def _bucket_findings(label: str, bucket: BucketStats, scope: str) -> list[Finding]:
    """Sentence for a tested bucket, its own reliability line and a pre-move caveat."""
    assert bucket.mean_car_0_1 is not None  # noqa: S101 - callers only pass tested buckets
    assert bucket.p_value is not None  # noqa: S101
    out = [
        Finding(
            text=(
                f"{scope}Around days with {label} news (that day and the next), the stock "
                f"{_reaction_phrase(bucket.mean_car_0_1)}."
            ),
            based_on_events=bucket.n,
        ),
        _reliability_finding(bucket.p_value, "a move this large", bucket.n, scope),
    ]
    pre = bucket.mean_car_pre_5
    if pre is not None and abs(pre) >= PRE_MOVE_CAVEAT:
        side = "better" if pre > 0 else "worse"
        out.append(
            Finding(
                text=(
                    f"{scope}Part of this move started before the news: in the 5 days before, "
                    f"the stock had already moved {_pct_abs(pre)} ({side} than expected)."
                ),
                based_on_events=bucket.n,
            )
        )
    return out


def _untested_finding(
    buckets: Sequence[tuple[str, BucketStats]], min_n: int, scope: str
) -> Finding:
    """One "not enough events" finding covering every bucket too thin to test."""
    if len(buckets) == 1:
        label, b = buckets[0]
        text = (
            f"{scope}Not enough {label}-news events yet to judge "
            f"(found {b.n}; need at least {min_n})."
        )
    else:
        found = " and ".join(f"{b.n} {label}-news" for label, b in buckets)
        text = (
            f"{scope}Not enough positive-news or negative-news events yet to judge "
            f"(found {found}; need at least {min_n} of each)."
        )
    return Finding(text=text, based_on_events=sum(b.n for _, b in buckets))


def _scope_findings(stats: MacroStats, scope: str) -> list[Finding]:
    """Findings for one scope; ``scope`` is a prefix such as "Excluding earnings periods: "."""
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
    out: list[Finding] = []
    untested: list[tuple[str, BucketStats]] = []
    labels: tuple[Bucket, Bucket] = ("positive", "negative")
    for label in labels:
        bucket = stats.buckets[label]
        if bucket.p_value is None or bucket.mean_car_0_1 is None:
            untested.append((label, bucket))
        else:
            out += _bucket_findings(label, bucket, scope)
    if untested:
        out.append(_untested_finding(untested, stats.min_n, scope))
    diff = stats.difference
    if diff is not None:
        total = diff.n_pos + diff.n_neg
        out.append(Finding(text=f"{scope}{_gap_sentence(diff.mean_diff)}", based_on_events=total))
        out.append(_reliability_finding(diff.p_value, "a gap this large", total, scope))
    corr = stats.correlation
    if corr is not None:
        if corr.label == "could_be_chance" or abs(corr.rho) < MIN_LINK:
            text = "No clear link between how positive the news was and how the stock moved."
        elif corr.rho > 0:
            text = "More positive news tended to go with better-than-expected moves."
        else:
            text = "More positive news tended to go with worse-than-expected moves."
        out.append(Finding(text=f"{scope}{text}", based_on_events=corr.n))
        out.append(_reliability_finding(corr.p_value, "a pattern this strong", corr.n, scope))
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

    The primary scope excludes earnings periods (cleaner, not confounded by results
    announcements). When that scope used exactly the same events as the all-events scope
    (equal counts, since one is a subset of the other), only one scope is emitted and it has
    no "Including/Excluding" prefix. ``headline_findings`` is primary plus the regime line.
    """
    secondary: list[Finding] = []
    if stats_ex_earnings.n_used == stats_all.n_used:
        primary = _scope_findings(stats_ex_earnings, "")
    else:
        primary = _scope_findings(stats_ex_earnings, "Excluding earnings periods: ")
        secondary = _scope_findings(stats_all, "Including earnings periods: ")
    headline = list(primary)
    if regime is not None:
        headline.append(_regime_finding(regime))
    return MacroReport(
        top_events=_top_events(events, session_articles, top_n),
        headline_findings=headline,
        primary_findings=primary,
        secondary_findings=secondary,
        stats_all=stats_all,
        stats_ex_earnings=stats_ex_earnings,
        regime=regime,
        timeline=list(timeline),
        events_total=len(events),
        events_insufficient=sum(1 for e in events if e.status != "ok"),
    )
