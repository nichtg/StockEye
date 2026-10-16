"""Company-name helpers for the news pipeline (pure)."""

import re
from collections import Counter
from collections.abc import Collection

_SUFFIXES = frozenset(
    {"inc", "corp", "corporation", "ltd", "limited", "holdings", "group", "co", "plc", "nv", "sa"}
)
_NAME_NOISE = re.compile(r"[^\w&\s-]")
_SPACES = re.compile(r"\s+")
_WORDS = re.compile(r"[a-z0-9]+")


def core_name(company_name: str) -> str:
    """Company name without legal suffixes and punctuation, e.g. "DBS Group Holdings Ltd" -> "DBS".

    Only trailing suffix words are stripped, so a name that is nothing but suffixes is kept whole.
    """
    cleaned = _SPACES.sub(" ", _NAME_NOISE.sub("", company_name.replace(".", ""))).strip()
    words = cleaned.split(" ")
    while len(words) > 1 and words[-1].lower() in _SUFFIXES:
        words.pop()
    return " ".join(words)


def ignore_tokens(symbol: str, company_name: str) -> set[str]:
    """Words every headline about the symbol shares: ticker parts and the company's core name.

    ("D05.SI" gives d05 and si; "Rocket Lab Holdings, Inc." gives rocket and lab.)
    """
    text = f"{symbol} {core_name(company_name)}"
    return {part for part in re.split(r"[^a-z0-9]+", text.lower()) if part}


def shared_words(titles: Collection[str], min_share: float = 0.5, min_titles: int = 10) -> set[str]:
    """Words found in at least ``min_share`` of ``titles``: a stand-in for the company name.

    For the startup backfill, which has no company name at hand. The name words dominate a
    symbol's headlines (the relevance filter requires them), so they are found this way; a few
    other very common words may come along; they are ignored too, as the name is.
    """
    if len(titles) < min_titles:  # too few to tell a name from a story: ignore nothing
        return set()
    counts: Counter[str] = Counter()
    for title in titles:
        counts.update(set(_WORDS.findall(title.lower())))
    need = min_share * len(titles)
    return {word for word, n in counts.items() if n >= need}
