"""Rule-based detector for low-value headlines (pure, no I/O).

Two families of headline carry no news and only add volume (and, for the macro study, repeated
or auto-generated "events"):

* **Fund holdings filings**: "Apple Inc. $AAPL Stake Cut by Denali Advisors LLC", "Acme Capital
  Buys 12,345 Shares of Apple Inc. $AAPL". These are auto-written from 13F filings, one per fund.
* **Quote tickers**: "Microsoft stock trades at EUR 447.90 after dividend hike", "Sandisk stock
  at USD 1,711.11 on September 28, 2026". A price stamp with no story.

Conservative by design: a wrongly dropped article is gone for good. So most filing rules also
want the filing's ticker mark ("$AAPL" or "(NASDAQ:AAPL)"), and a title that names an executive
role or an activist is left alone ("EVP Sells 2,200 Shares", "Elliott Builds $4 Billion Stake").

Known gaps: filings reworded to match none of the verbs below or lacking a ticker mark
("Mitsubishi UFJ Trust Quietly Adds 75,952 Shares of Rocket Lab ... in Latest SEC Disclosure" is
kept when unmarked), "$" quote stamps (only caught when the price ends the title or a date
follows it), and a quote ticker that carries real news in the same title ("Microsoft unveils X
and Microsoft stock trades at EUR 486.55" is dropped with the stamp). A miss only costs a stored
row; the opposite error costs a real article.
"""

import re

_FLAGS = re.IGNORECASE

# A person with a role, or an activist, is news and not a filing.
_INSIDER_OR_ACTIVIST = re.compile(
    r"\b(?:CEO|CFO|COO|CTO|CRO|CAO|EVP|SVP|VP|director|president|chairman|chairwoman|officer"
    r"|insider|chief|executive|founder|cofounder|counsel|activist|billionaire|Rep\.|Sen\.)"
    r"(?!\w)|\b(?:Elliott|Icahn|Starboard|Trian|Pershing)\b",
    _FLAGS,
)
# The ticker mark of an auto-written filing headline: "$AAPL" or "(NASDAQ:AAPL)" / "(MSFT)".
# Where it sits matters: in a filing it follows the verb ("Denali Cuts Position in Apple Inc.
# $AAPL"), in real news it names the actor ("Microsoft (MSFT) cuts stake in OpenAI").
_MARK = r"(?:\$[A-Z]{1,5}\b|\((?:[A-Z]+:\s*)?[A-Z0-9]{1,5}(?:\.[A-Z]{1,2})?\))"
_TICKER_MARK = re.compile(_MARK)
# Insider-trade format ("... Sells 7,000 Shares of Nebius Group (NASDAQ:NBIS) Stock") is news.
_INSIDER_FORMAT = re.compile(r"\)\s+(?:company\s+)?stock\s*$", _FLAGS)
# An institution as the actor: "... Cut by Denali Advisors LLC", "Purchased by Swedbank AB".
_INSTITUTION = re.compile(
    r"\b(?:LLC|L\.?P\.?|Inc\.?|Ltd\.?|Corp\.?|Co\.?|AB|AG|SA|N\.?V\.?|PLC|FSB|Management|Advisors?"
    r"|Advisory|Capital|Partners|Trust|Bank|Wealth|Investments?|Financial|Group|Fund|Asset"
    r"|Securities|Associates|Planning)\b"
)

_CHANGED = (
    r"(?:boosted|raised|lifted|lowered|cut|trimmed|reduced|lessened|increased|decreased"
    r"|grown|shrunk|upped|adjusted)"
)
# "Stake Cut by X", "Holdings Trimmed by X", "Stock Position Lowered by X",
# "Holdings in Apple Inc. Decreased by X". Singular only ("The stakes raised by ..." is prose).
_HOLDING_CHANGED_BY = re.compile(
    rf"\b(?:holdings?|stake|position)(?:\s+in\s+[^,:;|]{{1,60}}?)?\s+{_CHANGED}\s+by\b", _FLAGS
)

_ACT = (
    r"(?:increases?|increased|raises?|raised|boosts?|boosted|trims?|trimmed|cuts?|lowers?"
    r"|lowered|reduces?|reduced|decreases?|decreased|grows?|lifts?|lessens?|adds?)"
)
_TRADE = r"(?:newly\s+)?(?:buys|bought|purchases|purchased|acquires|acquired|sells|sold)"
# Filler a filing headline puts between the verb and the noun: "Stock", "Its", "12,345".
_FILL = r"(?:(?:stock|its|their|more|additional|\d[\d,]*)\s+){0,3}"
_HOLDING = r"(?:holdings?|stake|position)"
# Verb-led rules: each matches the verb phrase, and the ticker mark must come after its start.
_VERB_LED: tuple[re.Pattern[str], ...] = (
    # "Cuts Stock Position in", "Lowers Stake in", "Increases Holdings in", "Grows Position".
    re.compile(rf"\b{_ACT}\s+{_FILL}{_HOLDING}\b", _FLAGS),
    # "Acquires New Stake in", "Buys New Position in", "Takes Position in", "Opens New Position".
    # "new" is required for the buy/sell verbs: "Walmart sells stake in Japanese stores" is news.
    re.compile(
        rf"\b(?:{_TRADE}\s+{_FILL}new\s+{_HOLDING}\b"
        rf"|takes\s+(?:\$[\d.,]+\s*(?:million|billion|thousand)?\s+)?position\s+in\b"
        r"|opens\s+(?:a\s+)?new\s+position\b)",
        _FLAGS,
    ),
    # "Sells 3,233 Shares of X $AAPL", "Buys Shares of 6,682 X", "Acquires New Shares in X".
    # The count must be plain digits: "Berkshire Buys 5 Million Shares" is not matched.
    re.compile(rf"\b(?:{_TRADE}|adds)\s+(?:(?:new|\d[\d,]*)\s+)?shares\s+(?:of|in)\b", _FLAGS),
    # "Amundi Has $139.45 Million Stock Holdings in Nebius Group".
    re.compile(
        rf"\b(?:has|holds|owns)\s+\$[\d.,]+\s*(?:million|billion|thousand|[mbk])?\s+"
        rf"(?:in\s+)?(?:stock\s+)?{_HOLDING}\s+in\b",
        _FLAGS,
    ),
    # "Main Street Research Trims Costco (NASDAQ: COST) Stock Position by 1,093 Shares to 62,366".
    re.compile(
        rf"\b{_ACT}\s+[^,;|]{{1,60}}?\b(?:stock\s+)?{_HOLDING}\s+by\s+\d[\d,]*\s+shares\b",
        _FLAGS,
    ),
)
# "101,516 Shares of Apple Inc. $AAPL Purchased by Yukon Wealth Management": the mark sits
# inside the match.
_SHARES_BOUGHT_BY = re.compile(
    r"^\s*\d[\d,]*\s+shares\s+(?:of|in)\b.{1,80}?\b(?:newly\s+)?(?:bought|purchased|acquired|sold)"
    r"\s+by\b",
    _FLAGS,
)
# "Rocket Lab Corporation $RKLB Shares Acquired by Hsbc Holdings PLC", "... Shares Newly
# Purchased by Bank of America Corp DE": a cashtag first, the auto-written template.
_CASHTAG_SHARES_BY = re.compile(
    r"\$[A-Z]{1,5}\b.{0,40}?\bshares\s+(?:newly\s+)?(?:acquired|purchased|bought|sold)\s+by\b",
    _FLAGS,
)
# "Apple Inc. (AAPL): Renaissance Technologies Opens New Position",
# "Apple Inc. $AAPL Stock: HighTower Advisors LLC Lowers Stake": the mark leads, then a colon,
# then the actor and the verb, and the title ends with the noun.
_MARK_COLON_STYLE = re.compile(
    rf"{_MARK}(?:\s+stock)?:\s+[^:]{{1,80}}?\b(?:{_ACT}\s+(?:new\s+)?|opens\s+new\s+)"
    rf"{_HOLDING}\s*$",
    _FLAGS,
)

# "Microsoft stock trades at EUR 447.90 ...", "Sandisk stock at USD 1,711.11 on Sept ...".
# Currency codes are an auto-generated stamp, so anything may follow the figure.
_QUOTE_CODE = re.compile(
    r"\b(?:stock|shares?)\s+(?:trad(?:es|ing)\s+)?at\s+(?:EUR|USD|SGD|GBP)\s+\d[\d,]*(?:\.\d+)?",
    _FLAGS,
)
# "$" stamps are only a ticker when the price ends the title or is followed by a date:
# "Buy SOFI Stock At $27?" and "Why PepsiCo Stock at $146 Looks Mispriced" are commentary.
_QUOTE_DOLLAR = re.compile(
    r"\b(?:stock|shares?)\s+(?:trad(?:es|ing)\s+)?at\s+\$\d[\d,]*(?:\.\d+)?"
    r"(?:\s+on\s+[A-Z][a-z]+\s+\d{1,2},\s+\d{4})?\s*$",
    _FLAGS,
)
# Aggregator quote pages: "DBS Group Holdings Ltd (D05.SI) Stock Price, News, Quote & History".
_QUOTE_PAGE = re.compile(r"\bstock\s+price,\s+news,\s+quote\b", _FLAGS)


def _after_mark(rule: re.Pattern[str], title: str) -> bool:
    """The rule matches and a ticker mark appears at or after the match's start."""
    return any(_TICKER_MARK.search(title, m.start()) for m in rule.finditer(title))


def _filing(title: str) -> bool:
    if match := _HOLDING_CHANGED_BY.search(title):
        marked_before = _TICKER_MARK.search(title, 0, match.start()) is not None
        if marked_before or _INSTITUTION.search(title, match.end()):
            return True
    if _CASHTAG_SHARES_BY.search(title):
        return True
    if _INSIDER_FORMAT.search(title):
        return False
    if _SHARES_BOUGHT_BY.search(title) and _TICKER_MARK.search(title):
        return True
    return _MARK_COLON_STYLE.search(title) is not None or any(
        _after_mark(rule, title) for rule in _VERB_LED
    )


def is_low_value(title: str) -> bool:
    """True for a fund-holdings filing headline or a quote-ticker price stamp.

    Pure and deterministic on the title text alone; conservative toward keeping real news
    (insider trades, activist stakes, acquisitions, ratings and earnings are never matched).
    """
    if _QUOTE_CODE.search(title) or _QUOTE_PAGE.search(title):
        return True
    if _INSIDER_OR_ACTIVIST.search(title):
        return False
    return _QUOTE_DOLLAR.search(title) is not None or _filing(title)
