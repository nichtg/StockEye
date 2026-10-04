"""Assemble the macro report: top events with headlines and plain-English findings.

Finding text is written for non-statisticians: it never contains the bare letters used as
statistical symbols for sample size or probability. The raw p-value travels in
``Finding.p_value`` so the UI can show it in a "Details" row. Every finding is an average
over past news days, never a statement about today's price. Sentences say "On average" or
"Across N news days studied" and carry the day count. The counts are the sessions the study
selected (at most one per 6 trading days, earnings-excluded in that scope), hence "studied".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

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

Scope = Literal["all_events", "excluding_earnings"]

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
class EventPoint:
    """One evaluated event for the price chart (``car_0_1`` is a fraction, 0.01 = 1%)."""

    date: date
    car_0_1: float
    sentiment: float
    article_count: int
    near_earnings: bool
    headline: str | None


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
    events: list[EventPoint]  # every ok event with a car_0_1, sorted by date
    headline_findings: list[Finding]  # primary + regime, kept for compatibility
    primary_findings: list[Finding]  # shown first: ex-earnings scope (or the only scope)
    secondary_findings: list[Finding]  # all-events scope; the UI shows it under Details
    primary_scope: Scope  # which events the primary findings cover; data, never finding prose
    secondary_scope: Scope | None  # None when only one scope was emitted
    stats_all: MacroStats
    stats_ex_earnings: MacroStats
    regime: Regime | None
    timeline: list[TimelinePoint]
    events_total: int
    events_insufficient: int
    earnings_note: str | None  # set by ``_earnings_note``; None when it does not apply


def _pct_abs(x: float) -> str:
    return f"{abs(round(x * 100, 1)):.1f}%"


def _reliability_finding(p: float, what: str, based_on: int) -> Finding:
    """Reliability sentence; ``what`` is e.g. "a gap this large". The raw p stays in the field.

    The label and the "about X in 100" figure come from the same rounded value, so they can
    never disagree (for example "clear news effect ... about 5 in 100").
    """
    raw = round(p * 100)
    below_floor = raw < 1
    in_100 = max(1, raw)
    label = reliability_label(in_100 / 100)
    chance = "fewer than 1 in 100 times" if below_floor else f"about {in_100} in 100 times"
    if label == "clear_effect":
        only = "" if below_floor else "only "
        text = (
            f"Clear news effect: if news had no influence, {what} would appear "
            f"by chance {only}{chance}."
        )
    elif label == "possible_effect":
        text = f"Possible news effect: {what} would appear by chance {chance}."
    elif in_100 >= VERY_OFTEN_AT:
        text = (
            f"No clear news effect: {what} would very often appear by chance, "
            "too often to rule out luck."
        )
    else:
        text = (
            f"No clear news effect: {what} would appear by chance {chance}, "
            "too often to rule out luck."
        )
    return Finding(text=text, based_on_events=based_on, reliability=label, p_value=p)


def _reaction_phrase(m: float) -> str:
    """How the stock moved against its market-model expectation, in plain words."""
    rounded = round(m * 100, 1)
    if rounded == 0:
        return "moved in line with what the market predicted"
    side = "better" if rounded > 0 else "worse"
    return f"did {_pct_abs(m)} {side} than its usual relationship with the market would predict"


def _gap_sentence(mean_diff: float, n_pos: int, n_neg: int) -> str:
    """Positive-versus-negative comparison; a gap that rounds to zero has no direction."""
    rounded = round(mean_diff * 100, 1)
    lead = f"On average, the {n_pos} positive-news days studied did"
    tail = f"the {n_neg} negative-news days (that day and the next)."
    if rounded == 0:
        return f"{lead} about the same as {tail}"
    side = "better" if rounded > 0 else "worse"
    return f"{lead} {_pct_abs(mean_diff)} {side} than {tail}"


def _pre_move_finding(bucket: BucketStats, mean_car: float) -> Finding | None:
    """Caveat for a mean move in the 5 trading days before the news; None when it is small.

    Only claims "part of this move" when the earlier move has the same sign as the move
    itself; an opposite-sign earlier move is reported without that claim.
    """
    pre = bucket.mean_car_pre_5
    if pre is None or abs(pre) < PRE_MOVE_CAVEAT:
        return None
    side = "better" if pre > 0 else "worse"
    same_direction = round(mean_car * 100, 1) != 0 and (pre > 0) == (mean_car > 0)
    if same_direction:
        text = (
            "Part of this move started earlier: on average, in the 5 trading days before "
            f"these news days, the stock had already moved {_pct_abs(pre)} {side} than expected."
        )
    else:
        text = (
            "In the 5 trading days before these news days, the stock had on average moved "
            f"{_pct_abs(pre)} {side} than expected."
        )
    return Finding(text=text, based_on_events=bucket.n_car_pre_5)


def _bucket_findings(label: str, bucket: BucketStats) -> list[Finding]:
    """Sentence for a tested bucket, its own reliability line and a pre-move caveat."""
    assert bucket.mean_car_0_1 is not None  # noqa: S101 - callers only pass tested buckets
    assert bucket.p_value is not None  # noqa: S101
    out = [
        Finding(
            text=(
                f"On average, on {bucket.n} {label}-news days studied, the stock "
                f"{_reaction_phrase(bucket.mean_car_0_1)} (that day and the next)."
            ),
            based_on_events=bucket.n,
        ),
        _reliability_finding(bucket.p_value, "a move this large", bucket.n),
    ]
    caveat = _pre_move_finding(bucket, bucket.mean_car_0_1)
    if caveat is not None:
        out.append(caveat)
    return out


def _untested_finding(buckets: Sequence[tuple[str, BucketStats]], min_n: int) -> Finding:
    """One "not enough days" finding covering every bucket too thin to test."""
    if len(buckets) == 1:
        label, b = buckets[0]
        text = f"Not enough {label}-news days yet to judge (found {b.n}; need at least {min_n})."
    else:
        found = " and ".join(f"{b.n} {label}-news" for label, b in buckets)
        text = (
            "Not enough positive-news or negative-news days yet to judge "
            f"(found {found}; need at least {min_n} of each)."
        )
    return Finding(text=text, based_on_events=sum(b.n for _, b in buckets))


def _scope_findings(stats: MacroStats) -> list[Finding]:
    """Findings for one scope. The text carries no scope wording; the report records it."""
    if stats.n_used < stats.min_n:
        return [
            Finding(
                text=(
                    "Not enough news days yet to judge "
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
            out += _bucket_findings(label, bucket)
    if untested:
        out.append(_untested_finding(untested, stats.min_n))
    diff = stats.difference
    if diff is not None:
        total = diff.n_pos + diff.n_neg
        out.append(
            Finding(
                text=_gap_sentence(diff.mean_diff, diff.n_pos, diff.n_neg), based_on_events=total
            )
        )
        out.append(_reliability_finding(diff.p_value, "a gap this large", total))
    corr = stats.correlation
    if corr is not None:
        if corr.label == "no_clear_effect" or abs(corr.rho) < MIN_LINK:
            claim = (
                "there was no clear link between how positive the news was and how the stock "
                "moved compared with the market's prediction"
            )
        elif corr.rho > 0:
            claim = "more positive news tended to go with better-than-expected moves"
        else:
            claim = "more positive news tended to go with worse-than-expected moves"
        text = f"Across {corr.n} news days studied, {claim} (that day and the next)."
        out.append(Finding(text=text, based_on_events=corr.n))
        out.append(_reliability_finding(corr.p_value, "a pattern this strong", corr.n))
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


def _event_points(
    events: Sequence[EventResult], session_articles: Mapping[date, Sequence[ScoredArticle]]
) -> list[EventPoint]:
    out: list[EventPoint] = []
    for e in sorted(events, key=lambda e: e.date):
        if e.status != "ok" or e.car_0_1 is None:
            continue
        arts = sorted(
            session_articles.get(e.date, ()), key=lambda a: (-abs(a.score), a.published_at)
        )
        out.append(
            EventPoint(
                date=e.date,
                car_0_1=e.car_0_1,
                sentiment=e.sentiment,
                article_count=e.article_count,
                near_earnings=e.near_earnings,
                headline=arts[0].title if arts else None,
            )
        )
    return out


EARNINGS_NOTE = "This effect comes mostly from news around earnings releases."


def _has_clear_test(stats: MacroStats) -> bool:
    """True when the positive-vs-negative difference or any bucket test is a clear effect.

    The rank correlation is left out on purpose: the note explains the two headline claims
    ("positive days beat negative days", "this bucket moved"), not the weaker link statement.
    """
    if stats.difference is not None and stats.difference.label == "clear_effect":
        return True
    return any(b.label == "clear_effect" for b in stats.buckets.values())


def _earnings_note(stats_all: MacroStats, stats_ex: MacroStats) -> str | None:
    """Note for effects that vanish once earnings periods are excluded.

    Applies only when both scopes were emitted (the caller checks) and the all-days scope has
    a ``clear_effect`` in its difference or bucket tests while the ex-earnings scope has none.
    """
    if _has_clear_test(stats_all) and not _has_clear_test(stats_ex):
        return EARNINGS_NOTE
    return None


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
    (equal counts, since one is a subset of the other) they are identical: only one scope is
    emitted, named "all_events", and ``secondary_scope`` is None. ``headline_findings`` is
    primary plus the regime line. ``earnings_note`` is set only when both scopes exist and the
    effect is clear with earnings days included but not without them (see ``_earnings_note``).
    """
    primary = _scope_findings(stats_ex_earnings)
    primary_scope: Scope = "excluding_earnings"
    secondary: list[Finding] = []
    secondary_scope: Scope | None = None
    note: str | None = None
    if stats_ex_earnings.n_used == stats_all.n_used:
        primary_scope = "all_events"  # no event was excluded, so the two scopes are the same
    else:
        secondary = _scope_findings(stats_all)
        secondary_scope = "all_events"
        note = _earnings_note(stats_all, stats_ex_earnings)
    headline = list(primary)
    if regime is not None:
        headline.append(_regime_finding(regime))
    return MacroReport(
        top_events=_top_events(events, session_articles, top_n),
        events=_event_points(events, session_articles),
        headline_findings=headline,
        primary_findings=primary,
        secondary_findings=secondary,
        primary_scope=primary_scope,
        secondary_scope=secondary_scope,
        stats_all=stats_all,
        stats_ex_earnings=stats_ex_earnings,
        regime=regime,
        timeline=list(timeline),
        events_total=len(events),
        events_insufficient=sum(1 for e in events if e.status != "ok"),
        earnings_note=note,
    )
