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
# Insider-trade format ("... Sells 7,000 Shares of Nebius Group (NASDAQ:NBIS) Stock") is news.
_INSIDER_FORMAT = re.compile(r"\)\s+(?:company\s+)?stock\s*$", _FLAGS)
_TICKER_MARK = re.compile(r"\$[A-Z]{1,5}\b|\((?:[A-Z]+:\s*)?[A-Z0-9]{1,5}(?:\.[A-Z]{1,2})?\)")

_CHANGED = (
    r"(?:boosted|raised|lifted|lowered|cut|trimmed|reduced|lessened|increased|decreased"
    r"|grown|shrunk|upped|adjusted)"
)
# "Stake Cut by X", "Holdings Trimmed by X", "Stock Position Lowered by X",
# "Holdings in Apple Inc. Decreased by X". Specific enough to need no ticker mark.
_HOLDING_CHANGED_BY = re.compile(
    rf"\b(?:holdings?|stakes?|positions?)(?:\s+in\s+[^,:;|]{{1,60}}?)?\s+{_CHANGED}\s+by\b", _FLAGS
)

_ACT = (
    r"(?:increases?|increased|raises?|raised|boosts?|boosted|trims?|trimmed|cuts?|lowers?"
    r"|lowered|reduces?|reduced|decreases?|decreased|grows?|lifts?|lessens?|adds?)"
)
_TRADE = r"(?:buys|bought|purchases|purchased|acquires|acquired|sells|sold)"
# Filler a filing headline puts between the verb and the noun: "Stock", "Its", "12,345".
_FILL = r"(?:(?:stock|its|their|more|additional|\d[\d,]*)\s+){0,3}"
_HOLDING = r"(?:holdings?|stakes?|positions?)"
# Rules that need the ticker mark.
_MARKED: tuple[re.Pattern[str], ...] = (
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
    # "101,516 Shares of Apple Inc. $AAPL Purchased by Yukon Wealth Management".
    re.compile(
        r"^\s*\d[\d,]*\s+shares\s+(?:of|in)\b.{1,80}?\b(?:bought|purchased|acquired|sold)\s+by\b",
        _FLAGS,
    ),
    # "Rocket Lab Corporation $RKLB Shares Acquired by Hsbc Holdings PLC".
    re.compile(r"\bshares\s+(?:acquired|purchased|bought|sold)\s+by\b", _FLAGS),
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
    # "Renaissance Technologies Opens New Position", "Trims Stake" at the end of a marked title.
    re.compile(rf"\b{_ACT}\s+(?:new\s+)?{_HOLDING}\s*$", _FLAGS),
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


def is_low_value(title: str) -> bool:
    """True for a fund-holdings filing headline or a quote-ticker price stamp.

    Pure and deterministic on the title text alone; conservative toward keeping real news
    (insider trades, activist stakes, acquisitions, ratings and earnings are never matched).
    """
    insider = _INSIDER_OR_ACTIVIST.search(title) is not None
    if _QUOTE_CODE.search(title) or _QUOTE_PAGE.search(title):
        return True
    if insider:
        return False
    if _QUOTE_DOLLAR.search(title) or _HOLDING_CHANGED_BY.search(title):
        return True
    if _INSIDER_FORMAT.search(title) or _TICKER_MARK.search(title) is None:
        return False
    return any(rule.search(title) for rule in _MARKED)
