"""Low-value headline detector, tested on real titles from the stored news."""

import pytest

from app.domain.news import is_low_value

# Fund-holdings filings and quote tickers: all real titles.
LOW_VALUE = [
    "Apple Inc. $AAPL Stake Cut by Denali Advisors LLC",
    "Apple Inc. $AAPL Holdings Trimmed by Birch Capital Management LLC",
    "Apple Inc. $AAPL Stock Position Lowered by The Manufacturers Life Insurance Company",
    "Apple Inc. $AAPL Stock Holdings Boosted by First Financial Bank Trust Division",
    "Apple Inc. $AAPL Stock: HighTower Advisors LLC Lowers Stake",
    "Apple Inc. $AAPL Stock: Adelphi Trust Co Decreases Holdings",
    "Covington Investment Advisors Inc. Lowers Stake in Apple Inc. $AAPL",
    "CMH Wealth Management LLC Cuts Stock Position in Apple Inc. $AAPL",
    "Corient Private Wealth LLC Increases Stock Holdings in Rocket Lab Corporation $RKLB",
    "Bouvel Investment Partners LLC Buys New Stake in Rocket Lab Corporation $RKLB",
    "Ally Financial Inc. Acquires New Position in Apple Inc. $AAPL",
    "Bank of America Corp DE Takes Position in Rocket Lab Corporation $RKLB",
    "Altar Rock LLC Sells 3,233 Shares of Apple Inc. $AAPL",
    "Baird Financial Group Inc. Buys Shares of 6,682 Nebius Group N.V. $NBIS",
    "11,696 Shares of Apple Inc. $AAPL Purchased by Denver PWM LLC",
    "Rocket Lab Corporation $RKLB Shares Acquired by Hsbc Holdings PLC",
    "Meadowbrook Wealth Management LLC Has $264,000 Holdings in Costco Wholesale Corporation $COST",
    "Matrix Asset Management Increased Its Holdings in Microsoft Corporation (MSFT)",
    "Main Street Research Trims Costco (NASDAQ: COST) Stock Position by 1,093 Shares to 62,366",
    "Microsoft stock trades at EUR 447.90 after dividend hike",
    "DBS Group stock at EUR 51.69, 7.0 percent below its 52-week high",
    "Sandisk stock at USD 1,711.11 on September 28, 2026",
    "PepsiCo stock at USD 128.20 on September 28, 2026",
    "DBS Group Holdings Ltd (D05.SI) Stock Price, News, Quote & History",
    "Apple Inc. $AAPL Shares Newly Purchased by Bank of America Corp DE",
    "Apple Inc. $AAPL Shares Newly Acquired by Caisse de depot et placement du Quebec",
    "Apple Inc. $AAPL Shares Newly Bought by University of Wisconsin Foundation",
    "Apple Inc. (AAPL): Renaissance Technologies Opens New Position",
]

# Real news that looks a little like the above and must be kept.
NEWS = [
    "Activist Investor Elliott Builds $4 Billion Stake in PepsiCo",
    "Activist investor takes a $4 billion stake in PepsiCo, seeing a path to revive sales",
    "Costco Wholesale (NASDAQ:COST) EVP Claudine Adamo Sells 2,200 Shares of Stock",
    "Nebius Group (NASDAQ:NBIS) CTO Danila Shtan Sells 14,546 Shares of Stock",
    "Marc Boroditsky Sells 22,386 Shares of Nebius Group (NASDAQ:NBIS) Stock",
    "Apple (AAPL) legal chief sells shares at $332.01 under a prearranged trading plan.",
    "SoFi (SOFI) CEO Anthony Noto adds 13,888 shares in open-market buy",
    "Insider Sell: Daniel Bartlett Sells 1,325 Shares of Walmart Inc (WMT)",
    "Amazon will acquire Apple's 20% stake in satellite firm Globalstar",
    "Walmart sells stake in Japanese stores",
    "PepsiCo Boosts Stake in Celsius With $585 Million Deal",
    "Rocket Lab completes ATM equity program, sells shares in collared deals (RKLB:NASDAQ)",
    "Warren Buffett's Berkshire Buys Big Stake in Alphabet, Sells More Apple Shares",
    "Western Digital to sell Sandisk shares at $545 per share",
    "Why PepsiCo Stock at $146 Looks Mispriced After Its Q1 2026 Operating Income Recovery",
    "Buy SOFI Stock At $27?",
    "Apple raises iPhone prices as analysts upgrade the stock to buy",
    "Apple Q4 earnings beat estimates on strong services revenue",
    "Morgan Stanley upgrades Rocket Lab to overweight, raises price target",
    "DBS Is Said to Revise Malaysia's Alliance Bank Offer Proposal to 30% Stake",
    "Dutch court confirms Apple abused dominant position in dating apps",
    "Walton family holdings trust sells $403 million in Walmart (WMT) stock",
    "Microsoft (MSFT) cuts stake in OpenAI",
    "SoftBank (9984.T) raises stake in Arm",
    "Nvidia (NVDA) boosts stake in Intel with $5 billion investment",
    "Google parent (GOOGL) acquires new stake in Anthropic",
    "Intel stake cut by US government",
    "The stakes raised by Apple's antitrust trial",
    "Apple (AAPL) adds 5,000 shares of buyback",
]


@pytest.mark.parametrize("title", LOW_VALUE)
def test_is_low_value_holdings_filings_and_quote_tickers_are_dropped(title: str) -> None:
    assert is_low_value(title)


@pytest.mark.parametrize("title", NEWS)
def test_is_low_value_real_news_is_kept(title: str) -> None:
    assert not is_low_value(title)


def test_is_low_value_is_case_insensitive_and_pure() -> None:
    assert is_low_value("APPLE INC. $AAPL STAKE CUT BY DENALI ADVISORS LLC")
    assert is_low_value("Apple Inc. $AAPL Stake Cut by Denali Advisors LLC") == is_low_value(
        "Apple Inc. $AAPL Stake Cut by Denali Advisors LLC"
    )
