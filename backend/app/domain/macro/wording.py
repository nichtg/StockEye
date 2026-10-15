"""Shared number wording for macro findings and verdicts (one source, no import cycle)."""

from __future__ import annotations

from typing import Literal

from app.domain.macro.sentiment_stats import shown_in_100, shown_label

Direction = Literal[-1, 0, 1]
__all__ = [
    "VERY_OFTEN_AT",
    "Direction",
    "direction",
    "pct_abs",
    "pct_signed",
    "shown_in_100",
    "shown_label",
]

VERY_OFTEN_AT = 95  # "in 100" figure from which chance is described as "very often"


def direction(x: float) -> Direction:
    """Sign of a fractional return as the user sees it: 0 when it rounds to 0.0%."""
    rounded = round(x * 100, 1)
    return 1 if rounded > 0 else -1 if rounded < 0 else 0


def pct_abs(x: float) -> str:
    """Magnitude as a percentage with one decimal, e.g. 0.0123 -> "1.2%"."""
    return f"{abs(round(x * 100, 1)):.1f}%"


def pct_signed(x: float) -> str:
    """Percentage with an explicit sign ("+1.0%", "-0.4%"; no sign when it rounds to 0.0%)."""
    sign = {1: "+", -1: "-", 0: ""}[direction(x)]
    return f"{sign}{abs(round(x * 100, 1)):.1f}%"
