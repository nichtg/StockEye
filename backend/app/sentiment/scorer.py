"""Sentiment scoring contract shared by the service layer and concrete scorers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SentimentScore:
    """Class probabilities (sum to 1) for one text; ``score`` = positive - negative in [-1, 1]."""

    positive: float
    negative: float
    neutral: float

    @property
    def score(self) -> float:
        return self.positive - self.negative


class SentimentUnavailableError(Exception):
    """The sentiment model files are missing or corrupt."""


class SentimentScorer(Protocol):
    """Synchronous, CPU-bound scorer; async callers must use ``asyncio.to_thread``."""

    @property
    def model_version(self) -> str: ...

    def score(self, texts: Sequence[str]) -> list[SentimentScore]:
        """Return one score per input text, in order. Empty input gives an empty list."""
        ...
