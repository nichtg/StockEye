"""Rule-based detector for price-recap headlines (pure, no I/O).

A recap headline *reports* a price move that already happened ("Stock Drops 6% After ...").
FinBERT scores such headlines strongly because the price moved, so feeding them to the event
study is reverse causality: it inflates the measured news effect. They are excluded from the
macro analysis (never deleted from storage).

The rules are deliberately conservative about what counts as news: a headline that names a real
event *and* a move ("shares jump after FDA approval") is still a recap, because its sentiment
reflects the move. Headlines with no move language (results, guidance, deals, rating changes)
are kept, and percent figures about fundamentals ("revenue up 8%") or forecasts ("could rise
20%") are not price moves.

Known gap: a company as the subject with no "stock"/"shares" and no percent ("Apple falls after
earnings") is not caught; it is indistinguishable from real news without a model, so catching it
would risk dropping genuine articles.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.domain.macro.alignment import ScoredArticle

_FLAGS = re.IGNORECASE

# Past, present and -ing forms of price-move verbs. "up"/"down" are handled separately.
# "gains <noun>" ("gains traction", "gains a price target") is a figure of speech, not a move.
_GAIN = (
    r"(?:gains?|gained|gaining)"
    r"(?!\s+(?:spotlight|support|traction|momentum|ground|steam|attention|an?\s))"
)
# "moves to Nasdaq-100" is a listing, not a price move.
_MOVE = r"(?:moves?|moved)(?!\s+to\b)"
_VERBS = (
    r"(?:rises?|rose|rising|falls?|fell|falling|jumps?|jumped|jumping|drops?|dropped|dropping"
    r"|surges?|surged|surging|plunges?|plunged|plunging|soars?|soared|soaring|sinks?|sank"
    r"|sinking|slides?|slid|sliding|advances?|advanced|advancing|loses?|lost|losing"
    r"|climbs?|climbed|climbing|tumbles?|tumbled|tumbling|rall(?:y|ies|ied|ying)"
    r"|slips?|slipped|slipping|dips?|dipped|spikes?|spiked|sags?|sagged|sheds?"
    r"|crash(?:es|ed)?|skyrockets?|skyrocketed|pops?|popped|gaps?|gapped"
    r"|dives?|dived|dove|craters?|cratered|rockets?(?!\s+lab\b)|rocketed|rebounds?|rebounded"
    r"|slumps?|slumped"
    r"|retreats?|retreated|declines?|declined|edges?\s+(?:higher|lower)"
    rf"|extends?\s+(?:the\s+)?rally|{_GAIN}|{_MOVE})"
)
# "up" is only a direction when not "up for grabs" / "stock up on".
_DIR = r"(?:down|higher|lower|up(?!\s+(?:for|on)\b))"
_AUX = r"(?:(?:is|are|was|were|has|have|had|just|also|still|again|keeps?)\s+)*"
_NUM = r"[+-]?\d[\d.,]*"
_PCT = r"\s?(?:%|percent)"
# Filler between a move verb and its percent figure ("down by as much as 4.79%").
_FILL = (
    r"(?:\s+(?:by|as|much|about|over|nearly|more|than|around|roughly|another|almost|just"
    r"|up|down|\$?\d[\d.,]*))"
)

# Percent figure that is really a fundamentals/macro number, not a price move.
_FUNDAMENTALS = re.compile(
    r"\b(?:revenues?|sales|profits?|earnings|income|eps|margins?|dividends?|guidance|forecasts?"
    r"|deliveries|shipments|orders|bookings|growth|ebitda|cash\s+flow|rates?|inflation"
    r"|unemployment|gdp|output|production|demand|users|subscribers|spending|capex|costs?"
    r"|expenses|debt|loans?|payrolls?|pay|compensation|salar(?:y|ies)|wages?|jobs|prices\s+of"
    r"|rents?|fees|fcf|free\s+cash\s+flow|backlog|volume|targets?|upside)\b",
    _FLAGS,
)
# A stock-ish subject in the same clause overrides the fundamentals exclusion.
_STOCKISH = re.compile(
    r"\b(?:stocks?|shares?|share\s+price|stock\s+price|price(?!\s+target)|trading|trades?)\b"
    r"|\([A-Z.]*:[A-Z.]+\)",
    _FLAGS,
)
_CLAUSE_BREAK = re.compile(r"[,;:|\u2013\u2014]")
# "gains 12% market share" / "loses 5% of its workforce" / "up 10% from current levels" are
# not price moves that already happened.
_NOT_PRICE_AFTER = re.compile(
    r"\s*(?:of\s+(?:its|the)\s+\w+|market\s+share|stake|in\s+(?:revenue|sales|profit)"
    r"|year[- ]over[- ]year|yoy|annual|a\s+year|from\s+(?:current|today))",
    _FLAGS,
)
# "could surge 30%", "set to jump 40%", "can rise 1,500%": a forecast, not a reported move.
_FORWARD_LOOKING = re.compile(
    r"\b(?:could|can|may|might|will|would|to|set\s+to|poised\s+to|expected\s+to|potential\s+to)"
    r"\s+(?:\w+\s+)?$",
    _FLAGS,
)

# 1. Move verb (or up/down) followed by a percent: "AAPL Stock Drops 6%", "Moved Down by 4.79%",
#    "moved up by 4.79% on Jun 25".
_MOVE_PCT = re.compile(rf"\b(?:{_VERBS}|up|down){_FILL}{{0,4}}\s+({_NUM}){_PCT}", _FLAGS)

# Rules with no ambiguity about the subject; any match flags the headline.
_SIMPLE_RULES: tuple[re.Pattern[str], ...] = (
    # 2. "shares/stock (are) up/down/higher/lower" or "stock soars on ...": the stock is the
    #    mover. Also covers "Why X Stock Is Soaring Today". Optional "(NASDAQ:X)" in between.
    re.compile(rf"\b(?:stocks?|shares?)\s+(?:\([^)]*\)\s+)?{_AUX}(?:{_VERBS}|{_DIR})\b", _FLAGS),
    # 2b. "shares of Apple are down": same, with the company between.
    re.compile(
        rf"\b(?:shares|stock)\s+of\s+[^,:;|]{{1,40}}?\s+{_AUX}(?:{_VERBS}|{_DIR})\b", _FLAGS
    ),
    # 3. "Trading Up 34%", "trades lower": a trading-direction report.
    re.compile(r"\btrad(?:ing|es|ed)\s+(?:up|down|higher|lower|flat)\b", _FLAGS),
    # 4. "stock hits a new 52-week high/low": reports the price level reached.
    re.compile(
        r"\b(?:hits?|hit|rall(?:y|ies|ied)\s+to|reach(?:es|ed)?|touch(?:es|ed)?|notch(?:es|ed)?"
        r"|sets?|set)\s+(?:an?\s+)?(?:new\s+)?"
        r"(?:52[- ]week|all[- ]time|multi[- ]year|record)\s+(?:high|low)\b"
        r"(?!\s+(?:revenue|sales|profit|earnings|quarter|income|margin))",
        _FLAGS,
    ),
    # 5. "what's moving" and mover lists: market-action roundups, not news.
    re.compile(
        r"\bwhat(?:[\u2019']s|\s+is)\s+moving\b|\b(?:top|biggest|big|major|premarket|pre-market)"
        r"\s+(?:stock\s+)?movers\b|\bstocks?\s+making\s+(?:the\s+)?biggest\s+moves\b",
        _FLAGS,
    ),
    # 6. Noun form: "after a 12% gain".
    re.compile(rf"\bafter\s+an?\s+{_NUM}{_PCT}\s+(?:gain|drop|jump|decline|rise|fall)\b", _FLAGS),
    # 7. Zacks-style: "Apple outpaces stock market gains", "dips more than the market".
    re.compile(
        r"\b(?:outpaces\s+(?:the\s+)?stock\s+market"
        r"|(?:ascends|declines|dips|rises|falls|gains)\s+(?:more\s+than|while|as)\s+"
        r"(?:the\s+)?(?:broader\s+|overall\s+)?(?:stock\s+)?market"
        r"|lags\s+(?:the\s+)?(?:broader\s+)?(?:stock\s+)?market)\b",
        _FLAGS,
    ),
)


def _is_price_percent(title: str, match: re.Match[str]) -> bool:
    """True when the percent figure is a price move rather than a fundamentals number."""
    clause_start = max(
        (m.end() for m in _CLAUSE_BREAK.finditer(title, 0, match.start())), default=0
    )
    if _FORWARD_LOOKING.search(title[max(0, match.start() - 25) : match.start()]):
        return False
    prefix = title[clause_start : match.start()]
    if _FUNDAMENTALS.search(prefix) and not _STOCKISH.search(prefix):
        return False
    return _NOT_PRICE_AFTER.match(title, match.end()) is None


def is_price_recap(title: str) -> bool:
    """True when ``title`` reports a price move that already happened.

    Pure and deterministic on the title text alone; conservative toward keeping genuine news.
    """
    if any(rule.search(title) for rule in _SIMPLE_RULES):
        return True
    return any(_is_price_percent(title, m) for m in _MOVE_PCT.finditer(title))


def exclude_price_recaps(articles: Iterable[ScoredArticle]) -> list[ScoredArticle]:
    """Articles whose title is not a price recap; the macro analysis reads only these."""
    return [a for a in articles if not is_price_recap(a.title)]
