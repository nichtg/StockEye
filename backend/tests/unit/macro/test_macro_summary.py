import re
from datetime import UTC, date, datetime, timedelta

import pytest
from macro_helpers import make_event

from app.domain.macro import (
    BucketStats,
    Correlation,
    Difference,
    Finding,
    MacroStats,
    Regime,
    ScoredArticle,
    TimelinePoint,
    build_macro_report,
    compute_stats,
)

# A bare "n" or "p" reads as statistician shorthand; user text must never contain one.
BARE_SYMBOL = re.compile(r"(?<![A-Za-z0-9])[npNP](?![A-Za-z0-9])")


def _bucket(name: str, n: int, mean: float | None) -> BucketStats:
    return BucketStats(
        bucket=name,  # type: ignore[arg-type]
        n=n,
        mean_car_0_1=mean,
        median_car_0_1=mean,
        n_car_0_5=n,
        mean_car_0_5=mean,
        median_car_0_5=mean,
        mean_car_pre_5=None,
    )


def _stats(
    *,
    n_used: int = 34,
    pos: tuple[int, float | None] = (17, 0.008),
    neg: tuple[int, float | None] = (17, -0.004),
    difference: Difference | None = None,
    correlation: Correlation | None = None,
    exclude: bool = True,
) -> MacroStats:
    return MacroStats(
        exclude_near_earnings=exclude,
        min_n=10,
        n_used=n_used,
        correlation=correlation,
        buckets={
            "positive": _bucket("positive", *pos),
            "neutral": _bucket("neutral", 0, None),
            "negative": _bucket("negative", *neg),
        },
        difference=difference,
    )


def _diff(p: float, label: str) -> Difference:
    return Difference(
        mean_diff=0.012,
        t=2.5,
        p_value=p,
        label=label,
        n_pos=17,
        n_neg=17,  # type: ignore[arg-type]
    )


def _report(ex: MacroStats, allv: MacroStats | None = None, **kwargs):
    return build_macro_report([], allv or ex, ex, kwargs.pop("regime", None), [], {}, **kwargs)


def _texts(report) -> list[str]:
    return [f.text for f in report.headline_findings]


def test_build_macro_report_headline_follows_templates_for_positive_and_negative_news():
    report = _report(_stats())

    texts = _texts(report)
    assert (
        "Excluding earnings periods: After positive news, the stock beat the market by 0.8% "
        "on average over the next 2 days." in texts
    )
    assert (
        "Excluding earnings periods: After negative news, the stock lagged the market by 0.4% "
        "on average over the next 2 days." in texts
    )
    pos_finding = next(f for f in report.headline_findings if "positive news" in f.text)
    assert pos_finding.based_on_events == 17


@pytest.mark.parametrize(
    ("p", "label", "expected"),
    [
        (
            0.03,
            "likely_real",
            "Likely a real effect: if news had no influence, a gap this large would appear "
            "by chance only about 3 in 100 times.",
        ),
        (
            0.12,
            "weak_evidence",
            "Weak evidence: a gap this large would appear by chance about 12 in 100 times.",
        ),
        (
            0.5,
            "could_be_chance",
            "Could be chance: a gap this large would appear by chance about 50 in 100 times, "
            "too often to rule out luck.",
        ),
        (
            0.002,
            "likely_real",
            "Likely a real effect: if news had no influence, a gap this large would appear "
            "by chance fewer than 1 in 100 times.",
        ),
    ],
)
def test_build_macro_report_reliability_line_per_label_keeps_raw_p_in_field_only(
    p, label, expected
):
    report = _report(_stats(difference=_diff(p, label)))

    finding = next(f for f in report.headline_findings if f.reliability is not None)
    assert finding.p_value == p
    assert finding.reliability == label
    assert finding.based_on_events == 34
    assert finding.text == expected


def test_build_macro_report_gap_and_correlation_findings():
    corr = Correlation(rho=-0.31, p_value=0.2, n=34, label="could_be_chance")
    report = _report(_stats(difference=_diff(0.03, "likely_real"), correlation=corr))

    texts = _texts(report)
    assert any(
        "The gap between positive-news and negative-news reactions was +1.2%" in t for t in texts
    )
    assert any("worse market-adjusted moves (rank correlation -0.31)" in t for t in texts)
    assert any("Across 34 news events" in t for t in texts)
    assert sum(f.reliability is not None for f in report.headline_findings) == 4  # 2 scopes x 2


def test_build_macro_report_insufficient_events_gives_not_enough_message():
    report = _report(_stats(n_used=6))

    assert _texts(report)[0] == (
        "Excluding earnings periods: Not enough news events yet to judge "
        "(found 6; need at least 10)."
    )
    assert report.headline_findings[0].based_on_events == 6
    assert report.headline_findings[0].p_value is None


def test_build_macro_report_thin_bucket_gets_its_own_not_enough_message():
    report = _report(_stats(pos=(3, 0.02)))

    assert any(
        "Not enough positive-news events yet to judge (found 3; need at least 10)." in t
        for t in _texts(report)
    )
    assert any("After negative news" in t for t in _texts(report))


def test_build_macro_report_negative_zero_and_zero_effect_formatting():
    report = _report(
        _stats(pos=(17, 0.00001), neg=(17, -0.00001), difference=_diff(0.5, "could_be_chance"))
    )
    texts = _texts(report)
    assert any("beat the market by 0.0%" in t for t in texts)
    assert any("lagged the market by 0.0%" in t for t in texts)


def test_build_macro_report_findings_never_contain_bare_n_or_p():
    corr = Correlation(rho=0.4, p_value=0.01, n=34, label="likely_real")
    regime = Regime(0.3, 0.0, 1.5, 14, "more_positive_than_usual")
    for p, label in [(0.03, "likely_real"), (0.12, "weak_evidence"), (0.6, "could_be_chance")]:
        report = _report(_stats(difference=_diff(p, label), correlation=corr), regime=regime)
        report2 = _report(_stats(n_used=4))
        for f in [*report.headline_findings, *report2.headline_findings]:
            assert not BARE_SYMBOL.search(f.text), f.text


def test_build_macro_report_regime_finding_wording():
    regimes = {
        "more_positive_than_usual": "more positive than usual",
        "more_negative_than_usual": "more negative than usual",
        "typical": "about typical",
    }
    for label, phrase in regimes.items():
        report = _report(_stats(), regime=Regime(0.1, 0.0, 1.0, 14, label))  # type: ignore[arg-type]
        last = report.headline_findings[-1]
        assert phrase in last.text
        assert last.based_on_events == 14


def test_build_macro_report_passes_through_stats_timeline_and_counts():
    ex, allv = _stats(), _stats(exclude=False)
    events = [
        make_event(date(2024, 1, 2), 0.5, 0.01),
        make_event(date(2024, 1, 3), 0.5, None, ok=False),
    ]
    tl = [TimelinePoint(date(2024, 1, 5), 0.1, 3)]

    report = build_macro_report(events, allv, ex, None, tl, {})

    assert report.stats_all is allv
    assert report.stats_ex_earnings is ex
    assert report.timeline == tl
    assert report.regime is None
    assert (report.events_total, report.events_insufficient) == (2, 1)


def _art(day: date, score: float, title: str, minute: int = 0) -> ScoredArticle:
    ts = datetime(day.year, day.month, day.day, 12, minute, tzinfo=UTC)
    return ScoredArticle(
        published_at=ts, score=score, title=title, url=f"https://x/{title}", source="src"
    )


def test_build_macro_report_top_events_ranked_by_absolute_car_with_headlines():
    d = [date(2024, 1, 1) + timedelta(days=i) for i in range(5)]
    events = [
        make_event(d[0], 0.5, 0.01, car_0_5=0.02),
        make_event(d[1], -0.7, -0.05, near_earnings=True),
        make_event(d[2], 0.9, 0.03),
        make_event(d[3], 0.9, 0.09, ok=False),  # insufficient: never listed
        make_event(d[4], 0.9, None),  # no car_0_1: never listed
    ]
    arts = {
        d[1]: [
            _art(d[1], -0.2, "a", 1),
            _art(d[1], -0.9, "b", 2),
            _art(d[1], 0.5, "c", 3),
            _art(d[1], 0.1, "d", 4),
        ]
    }
    ex = _stats()

    report = build_macro_report(events, ex, ex, None, [], arts, top_n=2)

    assert [t.date for t in report.top_events] == [d[1], d[2]]
    top = report.top_events[0]
    assert top.car_0_1 == -0.05
    assert top.near_earnings is True
    assert [h.title for h in top.headlines] == ["b", "c", "a"]  # most extreme first, max 3
    assert top.headlines[0].url == "https://x/b"
    assert top.headlines[0].source == "src"
    assert report.top_events[1].headlines == []
    assert report.top_events[1].car_0_5 is None


def test_build_macro_report_end_to_end_with_compute_stats_has_findings():
    events = [
        make_event(date(2024, 1, 1) + timedelta(days=i), 0.6, 0.02 + 0.001 * i) for i in range(10)
    ]
    events += [
        make_event(date(2024, 2, 1) + timedelta(days=i), -0.6, -0.02 + 0.001 * i) for i in range(10)
    ]
    ex = compute_stats(events, exclude_near_earnings=True)
    allv = compute_stats(events, exclude_near_earnings=False)

    report = build_macro_report(events, allv, ex, None, [], {})

    assert all(isinstance(f, Finding) for f in report.headline_findings)
    reliab = [f for f in report.headline_findings if f.reliability]
    assert reliab
    assert all(f.reliability == "likely_real" and f.p_value is not None for f in reliab)


def test_build_macro_report_tiny_negative_gap_prints_as_plain_zero():
    diff = Difference(
        mean_diff=-0.00001, t=0.1, p_value=0.9, label="could_be_chance", n_pos=17, n_neg=17
    )

    report = _report(_stats(difference=diff))

    assert any("was +0.0% over the next 2 days" in t for t in _texts(report))
