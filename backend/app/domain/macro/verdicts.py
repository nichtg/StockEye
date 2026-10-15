"""Plain-question verdicts for the macro section (primary scope only).

Each verdict is a question, a one-word answer and one supporting sentence with no bare
statistical symbols. Labels come from ``shown_label``, the same rounded figure the findings
use, and a clear or possible effect that rounds to 0.0% is reported as "not clearly", never
as "the opposite".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.domain.macro.sentiment_stats import Bucket, MacroStats, Reliability
from app.domain.macro.wording import Direction, direction, pct_abs, pct_signed, shown_label

VerdictId = Literal["good_news", "bad_news", "overall"]
AnswerKind = Literal["clear", "possible", "none", "opposite", "insufficient"]

VALUE_STATEMENT = (
    "Shows whether news days for this stock moved its price more than the market alone "
    "would explain."
)
ANSWERS: dict[AnswerKind, str] = {
    "clear": "Yes, clearly",
    "possible": "Possibly",
    "none": "Not clearly",
    "opposite": "No, the opposite",
    "insufficient": "Not enough data",
}
_MOVE_CHANCE: dict[Reliability, str] = {
    "clear_effect": "A move this size rarely happens by chance.",
    "possible_effect": "A move this size could still happen by chance.",
    "no_clear_effect": "A move this size often happens by chance.",
}
_GAP_CHANCE: dict[Reliability, str] = {
    "clear_effect": "A gap this size rarely happens by chance.",
    "possible_effect": "A gap this size could still happen by chance.",
    "no_clear_effect": "A gap this size often happens by chance.",
}


@dataclass(frozen=True)
class Verdict:
    """A plain question, a one-word answer and one supporting sentence (primary scope)."""

    id: VerdictId
    question: str
    answer: str
    answer_kind: AnswerKind
    detail: str


def _days(n: int, what: str) -> str:
    return f"{n} day with {what}" if n == 1 else f"{n} days with {what}"


def _kind(label: Reliability, seen: Direction, expected: Direction) -> AnswerKind:
    """Answer kind for a tested effect.

    No clear effect, or an effect that rounds to 0.0%, is "none"; only then is the direction
    compared with the expected one, and a clear or possible effect the wrong way is "opposite".
    """
    if label == "no_clear_effect" or seen == 0:
        return "none"
    if seen != expected:
        return "opposite"
    return "clear" if label == "clear_effect" else "possible"


def _bucket_verdict(
    vid: VerdictId, question: str, bucket: Bucket, stats: MacroStats, *, expected: Direction
) -> Verdict:
    """Verdict for one news tone; ``expected`` is the direction the price should move."""
    b = stats.buckets[bucket]
    what = f"{bucket} news"
    if b.mean_car_0_1 is None or b.p_value is None:
        if b.n < stats.min_n:
            detail = f"Only {_days(b.n, what)} so far; at least {stats.min_n} are needed."
        else:
            detail = f"The {_days(b.n, what)} did not give a usable reading yet."
        return Verdict(vid, question, ANSWERS["insufficient"], "insufficient", detail)
    label = shown_label(b.p_value)
    kind = _kind(label, direction(b.mean_car_0_1), expected)
    detail = (
        f"On average {pct_signed(b.mean_car_0_1)} versus what the market predicted over 2 days, "
        f"across {_days(b.n, what)}. {_MOVE_CHANCE[label]}"
    )
    return Verdict(vid, question, ANSWERS[kind], kind, detail)


def _overall_verdict(stats: MacroStats) -> Verdict:
    """Positive-news days versus negative-news days, from the difference test only."""
    question = "Do good-news days beat bad-news days?"
    diff = stats.difference
    if diff is None:
        detail = (
            "Not enough days with both positive and negative news to compare them yet; "
            f"at least {stats.min_n} of each are needed."
        )
        return Verdict("overall", question, ANSWERS["insufficient"], "insufficient", detail)
    label = shown_label(diff.p_value)
    kind = _kind(label, direction(diff.mean_diff), 1)
    if kind in ("clear", "possible"):
        detail = (
            f"On average, positive-news days did {pct_abs(diff.mean_diff)} better than "
            "negative-news days over 2 days, compared with what the market predicted. "
            f"{_GAP_CHANCE[label]}"
        )
    elif kind == "opposite":
        detail = (
            f"Positive-news days did {pct_abs(diff.mean_diff)} worse than negative-news days "
            "on average over 2 days, the reverse of what the news suggested."
        )
    else:
        detail = (
            "Positive-news and negative-news days moved about the same against the market; "
            "any gap could easily be chance."
        )
    return Verdict("overall", question, ANSWERS[kind], kind, detail)


def build_verdicts(stats: MacroStats) -> list[Verdict]:
    """Good news, bad news and overall verdicts for one scope's statistics."""
    return [
        _bucket_verdict(
            "good_news", "Does good news lift the price?", "positive", stats, expected=1
        ),
        _bucket_verdict("bad_news", "Does bad news drag it down?", "negative", stats, expected=-1),
        _overall_verdict(stats),
    ]
