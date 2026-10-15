import re
from datetime import date, timedelta

import pytest
from macro_helpers import make_event

from app.domain.macro import (
    BucketStats,
    Difference,
    MacroStats,
    build_macro_report,
    compute_stats,
    reliability_label,
)
from app.services import analysis

AS_OF = date(2026, 10, 1)
# A bare "n" or "p" reads as statistician shorthand; user text must never contain one.
BARE_SYMBOL = re.compile(r"(?<![A-Za-z0-9])[npNP](?![A-Za-z0-9])")


def _bucket(name: str, n: int, mean: float | None, p: float | None = 0.03) -> BucketStats:
    tested = mean is not None and p is not None
    return BucketStats(
        bucket=name,  # type: ignore[arg-type]
        n=n,
        mean_car_0_1=mean,
        median_car_0_1=mean,
        n_car_0_5=n,
        mean_car_0_5=mean,
        median_car_0_5=mean,
        mean_car_pre_5=None,
        n_car_pre_5=0,
        t=2.0 if tested else None,
        p_value=p if tested else None,
        label=reliability_label(p) if p is not None and tested else None,
    )


def _stats(
    pos: BucketStats, neg: BucketStats, difference: Difference | None = None, n_used: int = 40
) -> MacroStats:
    return MacroStats(
        exclude_near_earnings=True,
        min_n=10,
        n_used=n_used,
        first_event=date(2025, 1, 6),
        last_event=date(2026, 9, 30),
        correlation=None,
        buckets={"positive": pos, "neutral": _bucket("neutral", 0, None), "negative": neg},
        difference=difference,
    )


def _diff(p: float, mean_diff: float = 0.012) -> Difference:
    return Difference(
        mean_diff=mean_diff,
        t=2.5,
        p_value=p,
        label=reliability_label(p),
        n_pos=17,
        n_neg=17,
    )


def _verdicts(stats: MacroStats, all_events: MacroStats | None = None) -> dict:
    report = build_macro_report([], all_events or stats, stats, None, [], {}, as_of=AS_OF)
    return {v.id: v for v in report.verdicts}


def test_bucket_ci_hand_computed_fixture_matches_t_interval() -> None:
    # mean 0.03, sd sqrt(2.5e-4), t(0.975, 4) = 2.776445: half-width = 0.019632
    cars = [0.01, 0.02, 0.03, 0.04, 0.05]
    events = [
        make_event(date(2025, 1, 6) + timedelta(days=10 * i), 0.5, c) for i, c in enumerate(cars)
    ]

    b = compute_stats(events, exclude_near_earnings=False).buckets["positive"]

    assert b.ci_low_0_1 == pytest.approx(0.030 - 0.019632, abs=1e-6)
    assert b.ci_high_0_1 == pytest.approx(0.030 + 0.019632, abs=1e-6)


def test_bucket_ci_single_event_is_none() -> None:
    events = [make_event(date(2025, 1, 6), 0.5, 0.02)]

    b = compute_stats(events, exclude_near_earnings=False).buckets["positive"]

    assert (b.ci_low_0_1, b.ci_high_0_1) == (None, None)


def test_bucket_ci_no_spread_is_none() -> None:
    events = [make_event(date(2025, 1, 6) + timedelta(days=i), 0.5, 0.02) for i in range(4)]

    b = compute_stats(events, exclude_near_earnings=False).buckets["positive"]

    assert (b.ci_low_0_1, b.ci_high_0_1) == (None, None)


def test_bucket_ci_excludes_zero_when_ttest_is_clear() -> None:
    cars = [0.01, 0.02, 0.03, 0.04, 0.05, 0.02, 0.03, 0.04, 0.03, 0.02]
    events = [
        make_event(date(2025, 1, 6) + timedelta(days=10 * i), 0.5, c) for i, c in enumerate(cars)
    ]

    b = compute_stats(events, exclude_near_earnings=False).buckets["positive"]

    assert b.label == "clear_effect"
    assert b.ci_low_0_1 is not None
    assert b.ci_low_0_1 > 0


def test_verdicts_report_has_three_in_order_and_value_statement() -> None:
    stats = _stats(_bucket("positive", 17, 0.01), _bucket("negative", 17, -0.01))

    report = build_macro_report([], stats, stats, None, [], {}, as_of=AS_OF)

    assert [v.id for v in report.verdicts] == ["good_news", "bad_news", "overall"]
    assert [v.question for v in report.verdicts] == [
        "Does good news lift the price?",
        "Does bad news drag it down?",
        "Does news move this stock more than the market?",
    ]
    assert report.value_statement == (
        "Shows whether news days for this stock moved its price more than the market alone "
        "would explain."
    )


@pytest.mark.parametrize(
    ("mean", "p", "kind", "answer"),
    [
        (0.012, 0.01, "clear", "Yes, clearly"),
        (0.012, 0.1, "possible", "Possibly"),
        (0.012, 0.6, "none", "Not clearly"),
        (-0.012, 0.01, "opposite", "No, the opposite"),
        (-0.012, 0.1, "opposite", "No, the opposite"),
    ],
)
def test_good_news_verdict_kind_follows_sign_and_reliability(
    mean: float, p: float, kind: str, answer: str
) -> None:
    stats = _stats(_bucket("positive", 21, mean, p), _bucket("negative", 17, -0.004))

    v = _verdicts(stats)["good_news"]

    assert (v.answer_kind, v.answer) == (kind, answer)


@pytest.mark.parametrize(
    ("mean", "p", "kind"),
    [
        (-0.012, 0.01, "clear"),
        (-0.012, 0.1, "possible"),
        (-0.012, 0.6, "none"),
        (0.012, 0.01, "opposite"),
    ],
)
def test_bad_news_verdict_is_sign_aware(mean: float, p: float, kind: str) -> None:
    stats = _stats(_bucket("positive", 17, 0.004), _bucket("negative", 21, mean, p))

    v = _verdicts(stats)["bad_news"]

    assert v.answer_kind == kind


def test_good_news_verdict_detail_states_average_count_and_chance() -> None:
    stats = _stats(_bucket("positive", 21, 0.0103, 0.5), _bucket("negative", 17, -0.004))

    v = _verdicts(stats)["good_news"]

    assert v.detail == (
        "On average +1.0% versus the market over 2 days, across 21 days with positive news. "
        "A gap this size often happens by chance."
    )


def test_bad_news_verdict_thin_bucket_is_insufficient_with_count() -> None:
    stats = _stats(_bucket("positive", 17, 0.004), _bucket("negative", 1, None))

    v = _verdicts(stats)["bad_news"]

    assert v.answer_kind == "insufficient"
    assert v.answer == "Not enough data"
    assert v.detail == "Only 1 day with negative news so far; at least 10 are needed."


def test_good_news_verdict_enough_days_but_no_spread_is_insufficient() -> None:
    stats = _stats(_bucket("positive", 12, None), _bucket("negative", 17, -0.004))

    v = _verdicts(stats)["good_news"]

    assert v.answer_kind == "insufficient"
    assert "12 days with positive news" in v.detail


def test_overall_verdict_clear_difference_is_clear() -> None:
    stats = _stats(_bucket("positive", 17, 0.01), _bucket("negative", 17, -0.01), _diff(0.01, 0.02))

    v = _verdicts(stats)["overall"]

    assert v.answer_kind == "clear"
    assert v.detail == "News days moved this stock more than the market explains."


def test_overall_verdict_no_clear_difference_says_in_line_with_market() -> None:
    stats = _stats(_bucket("positive", 17, 0.01), _bucket("negative", 17, -0.01), _diff(0.6, 0.002))

    v = _verdicts(stats)["overall"]

    assert v.answer_kind == "none"
    assert v.detail == "This stock's moves on news days were in line with the market's."


def test_overall_verdict_reversed_difference_is_opposite() -> None:
    stats = _stats(
        _bucket("positive", 17, -0.01), _bucket("negative", 17, 0.01), _diff(0.01, -0.02)
    )

    v = _verdicts(stats)["overall"]

    assert v.answer_kind == "opposite"
    assert "2.0% worse" in v.detail


def test_overall_verdict_possible_difference_is_possibly() -> None:
    stats = _stats(_bucket("positive", 17, 0.01), _bucket("negative", 17, -0.01), _diff(0.1, 0.02))

    assert _verdicts(stats)["overall"].answer_kind == "possible"


def test_overall_verdict_without_difference_uses_strongest_bucket() -> None:
    stats = _stats(_bucket("positive", 17, 0.01, 0.3), _bucket("negative", 17, -0.02, 0.01))

    assert _verdicts(stats)["overall"].answer_kind == "clear"


def test_overall_verdict_without_difference_strongest_bucket_wrong_way_is_opposite() -> None:
    stats = _stats(_bucket("positive", 17, -0.02, 0.01), _bucket("negative", 17, -0.01, 0.4))

    assert _verdicts(stats)["overall"].answer_kind == "opposite"


def test_overall_verdict_nothing_testable_is_insufficient() -> None:
    stats = _stats(_bucket("positive", 2, None), _bucket("negative", 3, None), n_used=5)

    v = _verdicts(stats)["overall"]

    assert v.answer_kind == "insufficient"
    assert "at least 10 of each" in v.detail


def test_verdicts_use_primary_scope_ex_earnings_when_scopes_differ() -> None:
    ex = _stats(_bucket("positive", 17, 0.012, 0.01), _bucket("negative", 17, -0.01), n_used=34)
    allv = _stats(_bucket("positive", 20, -0.012, 0.01), _bucket("negative", 20, -0.01), n_used=40)

    v = _verdicts(ex, allv)

    assert v["good_news"].answer_kind == "clear"  # all-events would read "opposite"


@pytest.mark.parametrize("p", [0.01, 0.1, 0.6])
@pytest.mark.parametrize("mean", [0.012, -0.012])
def test_verdict_text_never_contains_bare_statistical_symbols(mean: float, p: float) -> None:
    stats = _stats(_bucket("positive", 17, mean, p), _bucket("negative", 1, None), _diff(p, mean))
    thin = _stats(_bucket("positive", 2, None), _bucket("negative", 3, None), n_used=5)

    texts = [
        t for s in (stats, thin) for v in _verdicts(s).values() for t in (v.question, v.detail)
    ]

    assert texts
    assert not [t for t in texts if BARE_SYMBOL.search(t)]


def test_macro_cache_schema_bumped_so_stale_reports_are_rebuilt() -> None:
    assert analysis.MACRO_CACHE_SCHEMA == 8
    assert analysis.macro_cache_key("AAPL") == "macro:v8:AAPL"
