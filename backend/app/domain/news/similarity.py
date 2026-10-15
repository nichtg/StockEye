"""Near-duplicate headline detection (pure).

Lives in ``domain/news`` so the rule is testable without Mongo and stays under the
import-linter purity contract. It favours precision: a false merge hides one story behind
another (and averages opposite sentiments), while a missed merge only costs a repeated row.
"""

import re
from collections.abc import Collection, Hashable, Sequence

JACCARD_MIN = 0.5
CONTAINMENT_MIN = 0.8
MIN_SHARED = 3  # a match needs at least this many shared tokens
MIN_CONTAINMENT_SIZE = 3  # containment only counts when the smaller set is at least this big

_WORDS = re.compile(r"[a-z0-9]+")
_STOP_WORDS = frozenset(
    {
        *("a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have"),
        *("in", "is", "it", "its", "of", "on", "or", "says", "say", "said", "that", "the"),
        *("their", "this", "to", "was", "were", "will", "with", "after", "over", "new"),
    }
)
_SUFFIXES = ("ing", "ed", "es", "s")
_MIN_STEM = 3
_MIN_STEMMED_LENGTH = 5  # "news", "loss", "gain" stay as they are
_ES_AFTER = ("s", "x", "z", "ch", "sh")
_NEGATIONS = frozenset({"no", "not"})


def _stem(word: str) -> str:
    """Crude plural/tense stripping so "shares" and "share" meet; digits are left alone.

    Words of four letters or fewer are kept, and "s" is never stripped from "...ss".
    """
    if len(word) < _MIN_STEMMED_LENGTH:
        return word
    for suffix in _SUFFIXES:
        if suffix == "s" and word.endswith("ss"):
            continue
        if suffix == "es" and not word[:-2].endswith(_ES_AFTER):
            continue  # "shares" is share+s, but "launches" is launch+es
        if word.endswith(suffix) and len(word) - len(suffix) >= _MIN_STEM:
            return word[: -len(suffix)]
    return word


def _stems(words: str) -> frozenset[str]:
    return frozenset(_stem(w) for w in words.split())


# Words that say "later than planned", as stems (so "pushing" and "slipped" count too); folded
# to one token before comparing. Kept short: every entry is a chance of a false merge.
_DELAY = _stems(
    "push pushed pushes pushing postpone postponed postpones postponing "
    "slip slipped slips slipping delay delayed delays delaying"
)

# Opposite-direction words. If one headline has a word from one side and the other a word
# from the other side (and neither shares it), the stories disagree and never merge.
_POSITIVE = _stems(
    "up rise rises rose rising risen soar soars soared soaring surge surges surged jump "
    "jumps jumped gain gains gained rally rallies rallied upgrade upgrades upgraded buy "
    "buys bullish beat beats raise raises raised climb climbs climbed win wins won "
    "succeed succeeds succeeded high approve approves approved"
)
_NEGATIVE = _stems(
    "down fall falls fell falling plunge plunges plunged slump slumps slumped sink sinks "
    "sank drop drops dropped lose loses lost losing downgrade downgrades downgraded sell "
    "sells bearish miss misses missed cut cuts slide slides slid tumble tumbles tumbled "
    "fail fails failed low reject rejects rejected"
)


def _title_tokens(title: str, ignore: Collection[str] = ()) -> frozenset[str]:
    """Stemmed word set of ``title`` without punctuation, stop-words or ``ignore`` words.

    ``ignore`` is for the company name and ticker, which every headline about the symbol
    shares. Apostrophes split words; one-letter words are dropped (digits stay).
    """
    skip = _STOP_WORDS | {w.lower() for w in ignore}
    words = (w for w in _WORDS.findall(title.lower()) if w not in skip)
    return frozenset(
        "delay" if (stem := _stem(w)) in _DELAY else stem
        for w in words
        if len(w) > 1 or w.isdigit()
    )


def _opposed(only_a: frozenset[str], only_b: frozenset[str]) -> bool:
    return bool(
        (only_a & _POSITIVE and only_b & _NEGATIVE) or (only_a & _NEGATIVE and only_b & _POSITIVE)
    )


def _are_similar(a: frozenset[str], b: frozenset[str]) -> bool:
    shared = a & b
    if len(shared) < MIN_SHARED:
        return False
    only_a, only_b = a - b, b - a
    # Headlines that differ in a number (Q1/Q2, $100M/$50M) are different stories.
    if any(any(c.isdigit() for c in t) for t in only_a | only_b):
        return False
    if (only_a | only_b) & _NEGATIONS or _opposed(only_a, only_b):  # "not"/"no" in one title
        return False
    if len(shared) / len(a | b) >= JACCARD_MIN:
        return True
    smaller = min(len(a), len(b))
    return smaller >= MIN_CONTAINMENT_SIZE and len(shared) / smaller >= CONTAINMENT_MIN


def cluster_stories(
    items: Sequence[tuple[Hashable, str]], ignore: Collection[str] = ()
) -> list[list[int]]:
    """Groups of indexes of near-duplicate headlines published on the same day.

    ``items`` are ``(day, title)`` newest first, so the first index of a group is its main
    (newest) article and the rest keep that order. ``ignore`` holds company-name and ticker
    words. Two headlines match when they share at least three tokens, differ in no number, negation
    or opposite-direction word pair, and have Jaccard >= 0.5 or (for sets of 3+) one holds
    >= 80% of the other. Each entry is compared with the main article of each existing group
    of its day (no chaining, so groups cannot drift). Every index appears exactly once;
    groups are ordered by their main index.
    """
    tokens = [_title_tokens(title, ignore) for _, title in items]
    groups: list[list[int]] = []
    for i, (day, _) in enumerate(items):
        for group in groups:
            head = group[0]
            if items[head][0] == day and _are_similar(tokens[head], tokens[i]):
                group.append(i)
                break
        else:
            groups.append([i])
    return groups
