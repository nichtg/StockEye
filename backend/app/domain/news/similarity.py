"""Near-duplicate headline detection (pure).

Lives in ``domain/news`` so the rule is testable without Mongo and stays under the
import-linter purity contract.
"""

import re
from collections.abc import Collection, Hashable, Sequence

JACCARD_MIN = 0.5
CONTAINMENT_MIN = 0.8

_WORDS = re.compile(r"[a-z0-9]+")
_STOP_WORDS = frozenset(
    {
        *("a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have"),
        *("in", "is", "it", "its", "of", "on", "or", "says", "say", "said", "that", "the"),
        *("their", "this", "to", "was", "were", "will", "with", "after", "over", "new"),
    }
)


def title_tokens(title: str, ignore: Collection[str] = ()) -> frozenset[str]:
    """Lowercase word set of ``title`` without punctuation, stop-words or ``ignore`` tokens.

    ``ignore`` is for the company ticker/name, which every headline about the symbol shares.
    Apostrophes split words, so a possessive yields the noun and a one-letter token, which
    is dropped along with other one-letter words (digits stay).
    """
    words = _WORDS.findall(title.lower())
    skip = _STOP_WORDS | {w.lower() for w in ignore}
    return frozenset(w for w in words if (len(w) > 1 or w.isdigit()) and w not in skip)


def are_similar(a: frozenset[str], b: frozenset[str]) -> bool:
    """Jaccard >= 0.5, or the smaller set has at least 80% of its tokens in the other."""
    if not a or not b:
        return False
    shared = len(a & b)
    if shared / len(a | b) >= JACCARD_MIN:
        return True
    return shared / min(len(a), len(b)) >= CONTAINMENT_MIN


def cluster_stories(days: Sequence[Hashable], tokens: Sequence[frozenset[str]]) -> list[list[int]]:
    """Groups of indexes of same-``days`` entries with similar ``tokens``.

    Input is newest first, so the first index of a group is its main (newest) article and
    the rest keep that order. Each entry is compared with the main article of each existing
    group of its day (no chaining, so groups cannot drift). Every index appears exactly
    once; groups are ordered by their main index.
    """
    groups: list[list[int]] = []
    for i, day in enumerate(days):
        for group in groups:
            head = group[0]
            if days[head] == day and are_similar(tokens[head], tokens[i]):
                group.append(i)
                break
        else:
            groups.append([i])
    return groups
