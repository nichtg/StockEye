from datetime import UTC, date, datetime

import pytest
from macro_helpers import make_calendar, make_event

from app.domain.macro import (
    MacroStats,
    ScoredArticle,
    build_macro_report,
    compute_stats,
    daily_sentiment,
    exclude_price_recaps,
    is_price_recap,
)

RECAPS = [
    "Rocket Lab (NASDAQ:RKLB) Trading Up 34% After Analyst Upgrade",
    "Apple Inc Stock (AAPL) Moved Down by 4.79% on Jun 25: Drivers Behind the Movement",
    "AAPL Stock Drops 6% After Apple Passes AI-Driven Chip Costs to Consumers",
    "Why Rocket Lab Stock Is Soaring Today",
    "Apple shares jump after FDA approval of watch feature",
    "Tesla shares are down 5% in premarket trading",
    "Nvidia stock falls 3% as chip rally cools",
    "Microsoft (NASDAQ:MSFT) Shares Gap Down to $410",
    "Why Palantir Stock Plunged Today",
    "Apple stock hits new 52-week high",
    "Rocket Lab shares hit all-time high on launch news",
    "AAPL stock: what's moving Apple today",
    "Top movers: Apple, Tesla and Nvidia lead the premarket",
    "Apple Stock Climbs 2.1% Following iPhone Event",
    "Shares of Apple are up 4% after the keynote",
    "Rocket Lab Stock Surges 12% on Neutron Update",
    "Amazon (AMZN) Trading Lower Despite Strong Cloud Growth",
    "Apple Inc. (AAPL) stock is down 3% this week",
    "Why Nvidia shares are falling today",
    "Intel stock sinks 8% after weak outlook",
    "Apple slides 2% as investors weigh tariffs",
    "AAPL rises 1.5%, outperforming the broader market",
    "Rocket Lab (RKLB) Stock Rallies 9% Amid Space Contract Buzz",
    "Apple stock price drops 4% following court ruling",
    "Apple Stock Jumps 5%: Is It Time to Buy?",
    "Biggest movers in the S&P 500: Apple leads gainers",
    # A1: "stock <verb> on ..." names the cause but still reports the move.
    "Sandisk Stock Soars On Bullish Growth Outlook And AI Flash Bet",
    "ServiceNow Stock Tumbles On Q1 Earnings",
    "SoFi Technologies Stock Sinks on Soft Guidance",
    "Rocket Lab (RKLB) stock jumps on record-breaking contract",
    "Apple shares rise on strong quarterly sales",
    "ServiceNow Inc (NYSE:NOW) Beats Q4 Estimates but Stock Falls on Guidance",
    "Rocket Lab stock (NASDAQ:RKLB) slides to merger collar",
    "ServiceNow stock gains on a fresh Needham target",
    # A3: more forms.
    "Apple stock jumps 5 percent after the keynote",
    "Rocket Lab rises after a 12% gain in a single session, shares extend rally",
    "Apple outpaces stock market gains: what you should know",
    "Nvidia stock craters after export curbs",
    "Rocket Lab stock rockets on launch success",
    "Apple stock edges higher ahead of the event",
    "Tesla shares extend rally into the close",
    "Intel stock rebounds from lows",
    "Amazon stock slumps on retail worries",
    "Microsoft shares retreat from record",
    "Nvidia stock declines as chips weaken",
    "Apple moves up 3% in early trading",
    "Apple stock moves lower",
    "RKLB Rockets Higher As Defense Deals And Guidance Ignite Momentum",
    "RKLB Rockets Higher As Earnings, Defense Wins Fuel Breakout",
    "AAPL jumps higher after the keynote",
    "Intel trades lower on weak outlook",
    "Walmart stock dives into oversold territory, eyeing $100 support (WMT:NASDAQ)",
]

NEWS = [
    "Apple raises dividend 4%",
    "Rocket Lab wins $981M Space Force contract",
    "Apple Q3 revenue up 8% year over year",
    "Analyst upgrades Apple to Buy",
    "Apple unveils new iPhone with improved camera",
    "Rocket Lab announces Neutron rocket first launch date",
    "Apple beats earnings estimates on strong services growth",
    "Tesla recalls 200,000 vehicles over software issue",
    "Nvidia signs multi-year supply deal with major cloud provider",
    "Apple's iPhone sales rise 6% in China, Counterpoint says",
    "Microsoft raises full-year guidance after cloud strength",
    "Rocket Lab net income falls 12% as development costs climb",
    "SEC opens probe into Apple's app store practices",
    "Apple to cut 5% of retail workforce, report says",
    "Analyst raises Apple price target to $250",
    "Rocket Lab CEO says Neutron on track for next year",
    "Apple stock buyback program expanded to $110 billion",
    "Why Apple is investing in on-device AI",
    "Apple faces EU antitrust fine over streaming rules",
    "Amazon operating margin up 2 points on cost cuts",
    "Apple gains 12% market share in tablets, IDC finds",
    "How to stock up on iPhone accessories before the holidays",
    "Fed holds rates steady; inflation down to 2.9%",
    "Apple opens new campus in Austin",
    # A2: forecasts, price targets and fundamentals are not reported moves.
    "Rocket Lab (RKLB) Stock Could Surge 30%+ - What Analysts Are Betting On",
    "5 Reasons Why Sandisk Can Rise Another 1,500%",
    "ServiceNow To Rally More Than 18%? Here Are 10 Top Analyst Forecasts",
    "Here's Why PepsiCo Stock's FCF is Set to Jump 40%",
    "Walmart's Membership Fees Jump 17%",
    "SOFI Stock Gains Spotlight As Softer CPI Data Lifts Fintech",
    "Walmart Stock Gaining Steam Ahead of Debut on Nasdaq-100",
    "ServiceNow stock gains a higher 174 USD price target",
    "Apple price target raised to $250, up 10% from current levels",
    "Apple could rise 20%, analyst says",
    # A4: "up for grabs" is an idiom.
    "Why Apple Stock Is Up For Grabs",
    "Walmart aims higher with drone delivery",
    "Apple sets a higher bar for privacy",
    "Costco pays lower prices to suppliers under new contract",
    # Rule 7 is anchored to the Zacks phrasing; "market" in an industry sense is news.
    "Apple declines to comment on market rumors",
    "Apple lags rivals in smartphone market",
    "ServiceNow outpaces rivals in AI market",
    "Nvidia ascends to top of AI chip market",
    "Walmart lags Amazon in the online grocery market",
    "Apple outpaces Samsung in the smartphone market",
    "Top space stocks Rocket Lab and AST SpaceMobile to watch",
    "3 space stocks Rocket Lab investors should know",
    "Walmart stock moves to Nasdaq-100 listing",
]


def test_labelled_lists_are_large_enough():
    assert len(RECAPS) >= 20
    assert len(NEWS) >= 20
    assert len(RECAPS) + len(NEWS) >= 40


@pytest.mark.parametrize("title", RECAPS)
def test_is_price_recap_reported_price_move_is_flagged(title):
    assert is_price_recap(title) is True


@pytest.mark.parametrize("title", NEWS)
def test_is_price_recap_genuine_news_is_kept(title):
    assert is_price_recap(title) is False


def test_is_price_recap_is_case_insensitive():
    assert is_price_recap("APPLE STOCK DROPS 6% AFTER NEWS")
    assert is_price_recap("apple stock drops 6% after news")


def test_exclude_price_recaps_keeps_only_genuine_articles_in_order():
    arts = [_art(date(2024, 1, 2), 0.9, t) for t in (RECAPS[0], NEWS[0], RECAPS[1], NEWS[1])]

    kept = exclude_price_recaps(arts)

    assert [a.title for a in kept] == [NEWS[0], NEWS[1]]


def _art(day: date, score: float, title: str) -> ScoredArticle:
    ts = datetime(day.year, day.month, day.day, 12, 0, tzinfo=UTC)
    return ScoredArticle(ts, score, title, f"https://x/{abs(hash(title))}", "src")


def test_macro_report_event_headlines_contain_no_recap_after_exclusion():
    cal = make_calendar(date(2024, 1, 1), 10)
    day = cal.sessions[2]
    arts = [_art(day, 0.95, t) for t in RECAPS[:3]] + [_art(day, 0.1, t) for t in NEWS[:3]]
    events = [make_event(day, 0.4, 0.03, car_0_5=0.04)]
    stats: MacroStats = compute_stats(events, exclude_near_earnings=False)

    _, by_session = daily_sentiment(exclude_price_recaps(arts), cal)
    report = build_macro_report(events, stats, stats, None, [], by_session)

    titles = [h.title for t in report.top_events for h in t.headlines]
    assert titles  # guards against a vacuous pass
    assert not any(is_price_recap(t) for t in titles)
    assert report.events[0].headline is not None
    assert not is_price_recap(report.events[0].headline)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Apple CEO Pay Rises 18%; Company Opposes Anti-Diversity Measure", False),
        ("Rocket Lab Stock Advances 74% in 3 Months: Time to Take Profits?", True),
        ("Rocket Lab rallies to an all-time high as its M&A strategy impresses", True),
    ],
)
def test_is_price_recap_live_data_regressions(title, expected):
    assert is_price_recap(title) is expected
