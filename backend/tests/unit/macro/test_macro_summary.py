import re
from dataclasses import replace
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
    reliability_label,
)

# A bare "n" or "p" reads as statistician shorthand; user text must never contain one.
BARE_SYMBOL = re.compile(r"(?<![A-Za-z0-9])[npNP](?![A-Za-z0-9])")


def _bucket(
    name: str, n: int, mean: float | None, p: float | None = 0.03, pre: float | None = None
) -> BucketStats:
    tested = mean is not None and p is not None
    return BucketStats(
        bucket=name,  # type: ignore[arg-type]
        n=n,
        mean_car_0_1=mean,
        median_car_0_1=mean,
        n_car_0_5=n,
        mean_car_0_5=mean,
        median_car_0_5=mean,
        mean_car_pre_5=pre,
        n_car_pre_5=n if pre is not None else 0,
        t=2.0 if tested else None,
        p_value=p if tested else None,
        label=reliability_label(p) if p is not None and tested else None,
    )


def _stats(
    *,
    n_used: int = 34,
    pos: BucketStats | None = None,
    neg: BucketStats | None = None,
    difference: Difference | None = None,
    correlation: Correlation | None = None,
    exclude: bool = True,
) -> MacroStats:
    return MacroStats(
        exclude_near_earnings=exclude,
        min_n=10,
        n_used=n_used,
        first_event=date(2025, 1, 6),
        last_event=date(2026, 9, 30),
        correlation=correlation,
        buckets={
            "positive": pos or _bucket("positive", 17, 0.008),
            "neutral": _bucket("neutral", 0, None),
            "negative": neg or _bucket("negative", 17, -0.004),
        },
        difference=difference,
    )


def _diff(p: float, label: str = "clear_effect", mean_diff: float = 0.012) -> Difference:
    return Difference(
        mean_diff=mean_diff,
        t=2.5,
        p_value=p,
        label=label,  # type: ignore[arg-type]
        n_pos=17,
        n_neg=17,
    )


def _report(ex: MacroStats, allv: MacroStats | None = None, **kwargs):
    return build_macro_report([], allv or ex, ex, kwargs.pop("regime", None), [], {}, **kwargs)


def _texts(report) -> list[str]:
    return [f.text for f in report.headline_findings]


NO_LINK = (
    "Across 34 news days studied, there was no clear link between how positive the news was "
    "and how the stock moved compared with the market's prediction (that day and the next)."
)


def test_build_macro_report_bucket_sentences_use_market_model_wording():
    report = _report(_stats())

    texts = _texts(report)
    assert (
        "On average, on 17 positive-news days studied, the stock did 0.8% better than "
        "its usual relationship with the market would predict (that day and the next)." in texts
    )
    assert (
        "On average, on 17 negative-news days studied, the stock did 0.4% worse than "
        "its usual relationship with the market would predict (that day and the next)." in texts
    )
    pos_finding = next(
        f for f in report.headline_findings if "positive-news days studied" in f.text
    )
    assert pos_finding.based_on_events == 17


def test_build_macro_report_each_bucket_sentence_is_followed_by_its_own_reliability_line():
    pos = _bucket("positive", 17, 0.008, p=0.03)
    neg = _bucket("negative", 14, -0.004, p=0.4)

    findings = _report(_stats(pos=pos, neg=neg)).headline_findings

    assert "positive-news days studied" in findings[0].text
    assert findings[1].p_value == 0.03
    assert findings[1].reliability == "clear_effect"
    assert findings[1].based_on_events == 17
    assert "negative-news days studied" in findings[2].text
    assert findings[3].p_value == 0.4
    assert findings[3].reliability == "no_clear_effect"
    assert findings[3].based_on_events == 14


@pytest.mark.parametrize(
    ("p", "label", "expected"),
    [
        (
            0.03,
            "clear_effect",
            "Clear news effect: if news had no influence, a gap this large would appear "
            "by chance only about 3 in 100 times.",
        ),
        (
            0.12,
            "possible_effect",
            "Possible news effect: a gap this large would appear by chance about 12 in 100 times.",
        ),
        (
            0.5,
            "no_clear_effect",
            "No clear news effect: a gap this large would appear by chance about 50 in 100 times, "
            "too often to rule out luck.",
        ),
        (
            0.002,
            "clear_effect",
            "Clear news effect: if news had no influence, a gap this large would appear "
            "by chance fewer than 1 in 100 times.",
        ),
        (  # 0.049 prints as 5 in 100, so the label must agree with the printed figure
            0.049,
            "possible_effect",
            "Possible news effect: a gap this large would appear by chance about 5 in 100 times.",
        ),
        (  # 0.196 prints as 20 in 100: could be chance, not weak evidence
            0.196,
            "no_clear_effect",
            "No clear news effect: a gap this large would appear by chance about 20 in 100 times, "
            "too often to rule out luck.",
        ),
        (
            0.97,
            "no_clear_effect",
            "No clear news effect: a gap this large would very often appear by chance, "
            "too often to rule out luck.",
        ),
    ],
)
def test_build_macro_report_reliability_line_per_label_keeps_raw_p_in_field_only(
    p, label, expected
):
    report = _report(_stats(difference=_diff(p)))

    finding = next(f for f in report.headline_findings if "a gap this large" in f.text)
    assert finding.p_value == p
    assert finding.reliability == label
    assert finding.based_on_events == 34
    assert finding.text == expected


def test_build_macro_report_gap_is_worded_as_a_comparison():
    report = _report(_stats(difference=_diff(0.03, mean_diff=0.011)))
    assert (
        "On average, the 17 positive-news days studied did 1.1% better than the 17 "
        "negative-news days (that day and the next)." in _texts(report)
    )

    worse = _report(_stats(difference=_diff(0.03, mean_diff=-0.011)))
    assert (
        "On average, the 17 positive-news days studied did 1.1% worse than the 17 "
        "negative-news days (that day and the next)." in _texts(worse)
    )


def test_build_macro_report_tiny_gap_is_the_same_not_a_signed_zero():
    report = _report(_stats(difference=_diff(0.9, "no_clear_effect", mean_diff=-0.00001)))

    expected = (
        "On average, the 17 positive-news days studied did about the same as the 17 "
        "negative-news days (that day and the next)."
    )
    assert expected in _texts(report)


@pytest.mark.parametrize(
    ("rho", "p", "label", "expected"),
    [
        (
            0.4,
            0.01,
            "clear_effect",
            "Across 34 news days studied, more positive news tended to go with "
            "better-than-expected moves (that day and the next).",
        ),
        (
            -0.4,
            0.01,
            "clear_effect",
            "Across 34 news days studied, more positive news tended to go with "
            "worse-than-expected moves (that day and the next).",
        ),
        (0.4, 0.5, "no_clear_effect", NO_LINK),
        (0.05, 0.01, "clear_effect", NO_LINK),
        (0.0, 0.01, "clear_effect", NO_LINK),
    ],
)
def test_build_macro_report_correlation_wording_never_implies_direction_without_evidence(
    rho, p, label, expected
):
    corr = Correlation(rho=rho, p_value=p, n=34, label=label)

    report = _report(_stats(correlation=corr))

    assert expected in _texts(report)
    finding = next(f for f in report.headline_findings if "a pattern this strong" in f.text)
    assert finding.based_on_events == 34


def test_build_macro_report_untested_bucket_gets_no_sentence_only_not_enough_finding():
    report = _report(_stats(pos=_bucket("positive", 3, 0.02, p=None)))

    texts = _texts(report)
    assert "Not enough positive-news days yet to judge (found 3; need at least 10)." in texts
    assert not any("positive-news days studied" in t for t in texts)
    assert any("negative-news days studied" in t for t in texts)


def test_build_macro_report_two_untested_buckets_share_one_not_enough_finding():
    report = _report(
        _stats(pos=_bucket("positive", 3, 0.02, p=None), neg=_bucket("negative", 4, -0.01, p=None))
    )

    not_enough = [t for t in _texts(report) if t.startswith("Not enough")]
    assert not_enough == [
        "Not enough positive-news or negative-news days yet to judge "
        "(found 3 positive-news and 4 negative-news; need at least 10 of each)."
    ]
    assert not any("days studied" in t for t in _texts(report))


def test_build_macro_report_pre_move_same_sign_as_bucket_says_part_of_this_move():
    report = _report(_stats(pos=_bucket("positive", 17, 0.008, pre=0.013)))
    assert (
        "Part of this move started earlier: on average, in the 5 trading days before these "
        "news days, the stock had already moved 1.3% better than expected." in _texts(report)
    )
    caveat = next(f for f in report.headline_findings if "started earlier" in f.text)
    assert caveat.based_on_events == 17

    worse = _report(_stats(neg=_bucket("negative", 14, -0.004, pre=-0.012)))
    assert (
        "Part of this move started earlier: on average, in the 5 trading days before these "
        "news days, the stock had already moved 1.2% worse than expected." in _texts(worse)
    )


def test_build_macro_report_pre_move_opposite_sign_makes_no_part_of_this_move_claim():
    report = _report(_stats(pos=_bucket("positive", 17, 0.008, pre=-0.012)))

    texts = _texts(report)
    assert (
        "In the 5 trading days before these news days, the stock had on average moved "
        "1.2% worse than expected." in texts
    )
    assert not any("Part of this move" in t for t in texts)


def test_build_macro_report_pre_move_caveat_counts_its_own_events():
    pos = replace(_bucket("positive", 17, 0.008, pre=0.013), n_car_pre_5=11)

    report = _report(_stats(pos=pos))

    caveat = next(f for f in report.headline_findings if "5 trading days" in f.text)
    assert caveat.based_on_events == 11


def test_build_macro_report_small_pre_move_gets_no_caveat():
    small = _report(_stats(pos=_bucket("positive", 17, 0.008, pre=0.009)))
    assert not any("5 trading days" in t for t in _texts(small))


def test_build_macro_report_zero_bucket_effect_is_in_line_with_market():
    report = _report(
        _stats(pos=_bucket("positive", 17, 0.00001), neg=_bucket("negative", 17, -0.00001))
    )

    texts = _texts(report)
    assert (
        "On average, on 17 positive-news days studied, the stock moved in line with "
        "what the market predicted (that day and the next)." in texts
    )
    assert (
        "On average, on 17 negative-news days studied, the stock moved in line with "
        "what the market predicted (that day and the next)." in texts
    )


def test_build_macro_report_insufficient_events_gives_not_enough_message():
    report = _report(_stats(n_used=6))

    assert _texts(report)[0] == "Not enough news days yet to judge (found 6; need at least 10)."
    assert report.headline_findings[0].based_on_events == 6
    assert report.headline_findings[0].p_value is None


def test_build_macro_report_distinct_scopes_put_ex_earnings_first_and_other_in_secondary():
    ex = _stats(n_used=30)
    allv = _stats(n_used=34, pos=_bucket("positive", 20, 0.02), exclude=False)
    regime = Regime(0.1, 0.0, 1.0, 14, "typical")

    report = _report(ex, allv, regime=regime)

    assert report.primary_findings[0].text.startswith("On average, on 17 positive-news days")
    assert report.secondary_findings
    assert report.primary_scope == "excluding_earnings"
    assert report.secondary_scope == "all_events"
    assert not any("earnings periods" in t for t in _texts(report))
    assert report.headline_findings[:-1] == report.primary_findings
    assert "typical" in report.headline_findings[-1].text
    assert not any(f is g for f in report.secondary_findings for g in report.headline_findings)


def test_build_macro_report_identical_scopes_are_emitted_once_without_prefix():
    ex = _stats(n_used=34)
    allv = _stats(n_used=34, exclude=False)

    report = _report(ex, allv)

    assert report.secondary_findings == []
    assert report.primary_scope == "all_events"  # nothing was excluded, so the scopes coincide
    assert report.secondary_scope is None
    assert report.primary_findings
    assert not any("earnings periods" in t for t in _texts(report))


def test_build_macro_report_findings_never_contain_bare_n_or_p():
    corr = Correlation(rho=0.4, p_value=0.01, n=34, label="clear_effect")
    regime = Regime(0.3, 0.0, 1.5, 14, "more_positive_than_usual")
    for p in (0.03, 0.12, 0.6, 0.99):
        pos = _bucket("positive", 17, 0.008, p=p, pre=0.02)
        ex = _stats(pos=pos, difference=_diff(p), correlation=corr)
        allv = _stats(n_used=40, pos=pos, difference=_diff(p), correlation=corr, exclude=False)
        reports = [
            _report(ex, allv, regime=regime),
            _report(_stats(n_used=4)),
            _report(_stats(pos=_bucket("positive", 3, 0.1, p=None))),
        ]
        for report in reports:
            every = [*report.primary_findings, *report.secondary_findings]
            for f in [*every, *report.headline_findings]:
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
    assert all(f.reliability == "clear_effect" and f.p_value is not None for f in reliab)


def test_build_macro_report_events_sorted_ok_only_with_headline_mapping():
    d = [date(2024, 1, 1) + timedelta(days=i) for i in range(4)]
    events = [
        make_event(d[2], 0.9, 0.03),
        make_event(d[0], 0.5, -0.01, near_earnings=True),
        make_event(d[3], 0.9, 0.09, ok=False),  # insufficient: never listed
        make_event(d[1], 0.9, None),  # no car_0_1: never listed
    ]
    arts = {d[0]: [_art(d[0], 0.1, "mild", 1), _art(d[0], -0.8, "big", 2)]}
    ex = _stats()

    report = build_macro_report(events, ex, ex, None, [], arts, top_n=1)

    assert [e.date for e in report.events] == [d[0], d[2]]
    assert report.events[0].headline == "big"  # most extreme story
    assert report.events[0].near_earnings is True
    assert report.events[0].car_0_1 == -0.01
    assert report.events[1].headline is None
    assert len(report.top_events) == 1  # top_events is unaffected by the full list


def _earn_stats(label_p: float | None, *, n_used: int, exclude: bool) -> MacroStats:
    diff = None if label_p is None else _diff(label_p, reliability_label(label_p))
    return _stats(
        n_used=n_used,
        pos=_bucket("positive", 17, 0.008, p=0.5),
        neg=_bucket("negative", 17, -0.004, p=0.5),
        difference=diff,
        exclude=exclude,
    )


def test_build_macro_report_effect_only_with_earnings_days_gets_earnings_note():
    ex = _earn_stats(0.5, n_used=30, exclude=True)
    allv = _earn_stats(0.01, n_used=34, exclude=False)

    report = _report(ex, allv)

    assert report.earnings_note == "This effect comes mostly from news around earnings releases."


def test_build_macro_report_all_days_clear_bucket_test_gets_earnings_note():
    ex = _earn_stats(0.5, n_used=30, exclude=True)
    allv = _stats(n_used=34, pos=_bucket("positive", 20, 0.02, p=0.01), exclude=False)

    assert _report(ex, allv).earnings_note is not None


@pytest.mark.parametrize(
    ("p_ex", "p_all", "n_ex", "n_all"),
    [
        (0.01, 0.01, 30, 34),  # clear without earnings too
        (0.5, 0.5, 30, 34),  # nothing clear anywhere
        (0.5, 0.01, 34, 34),  # scopes identical: a single scope is emitted
    ],
)
def test_build_macro_report_earnings_note_absent_when_rule_does_not_apply(p_ex, p_all, n_ex, n_all):
    ex = _earn_stats(p_ex, n_used=n_ex, exclude=True)
    allv = _earn_stats(p_all, n_used=n_all, exclude=False)

    assert _report(ex, allv).earnings_note is None


def test_build_macro_report_correlation_sentence_leads_with_its_own_day_count():
    corr = Correlation(rho=0.4, p_value=0.01, n=29, label="clear_effect")

    texts = _texts(_report(_stats(correlation=corr)))

    assert (
        "Across 29 news days studied, more positive news tended to go with "
        "better-than-expected moves (that day and the next)." in texts
    )


def test_build_macro_report_pre_move_with_zero_rounded_bucket_mean_makes_no_part_claim():
    report = _report(_stats(pos=_bucket("positive", 17, 0.0004, pre=0.013)))

    texts = _texts(report)
    assert (
        "On average, on 17 positive-news days studied, the stock moved in line with "
        "what the market predicted (that day and the next)." in texts
    )
    assert (
        "In the 5 trading days before these news days, the stock had on average moved "
        "1.3% better than expected." in texts
    )
    assert not any("Part of this move" in t for t in texts)


def test_build_macro_report_findings_never_contain_bare_n_or_p_tokens():
    corr = Correlation(rho=0.4, p_value=0.01, n=29, label="clear_effect")
    full = _stats(
        pos=_bucket("positive", 17, 0.008, pre=0.013),  # same sign: "Part of this move"
        neg=_bucket("negative", 12, -0.004, pre=0.013),  # opposite sign
        difference=_diff(0.03),
        correlation=corr,
    )
    reports = [
        _report(full),
        _report(
            _stats(correlation=Correlation(rho=0.0, p_value=0.9, n=29, label="no_clear_effect"))
        ),
        _report(_stats(pos=_bucket("positive", 5, 0.01, p=None))),  # one untested bucket
        _report(
            _stats(
                pos=_bucket("positive", 5, 0.01, p=None), neg=_bucket("negative", 3, 0.0, p=None)
            )
        ),
        _report(_stats(n_used=4)),  # overall not enough
    ]

    texts = [t for r in reports for t in _texts(r)]
    assert any("Part of this move" in t for t in texts)
    assert any(t.startswith("In the 5 trading days") for t in texts)
    assert any(t.startswith("Not enough positive-news or negative-news") for t in texts)
    assert any(t.startswith("Across 29 news days") for t in texts)
    for text in texts:
        assert not BARE_SYMBOL.search(text), text
