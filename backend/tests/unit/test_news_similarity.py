"""Near-duplicate headline grouping: pure rules, no I/O."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.domain.news import InvalidMonthError, cluster_stories, month_window

DAY = date(2026, 10, 2)
NEXT_DAY = date(2026, 10, 1)
IGNORE = {"rklb", "rocket", "lab"}  # ticker and company name, as the feed passes them


def _groups(titles: list[str], days: list[date] | None = None) -> list[list[int]]:
    days = days or [DAY] * len(titles)
    return cluster_stories(list(zip(days, titles, strict=True)), IGNORE)


def test_cluster_stories_same_neutron_delay_from_three_outlets_groups() -> None:
    groups = _groups(
        [
            "Rocket Lab delays Neutron launch to 2027",
            "Rocket Lab's Neutron rocket delayed to 2027",
            "Rocket Lab delays Neutron debut to 2027",
        ]
    )

    assert groups == [[0, 1, 2]]


def test_cluster_stories_loosely_worded_reports_stay_apart_for_precision() -> None:
    # Realistic rewrites of one story share too few words to merge safely.
    groups = _groups(
        [
            "Rocket Lab delays Neutron rocket's first launch to 2027, updating its development "
            "timeline.",
            "Rocket Lab Updates Neutron Development Schedule, Targets Inaugural Launch in 2027",
            "Rocket Lab Announces Delay of Neutron Rocket's Maiden Launch to Next Year",
        ]
    )

    assert groups == [[0], [1], [2]]


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Rocket Lab stock soars", "Rocket Lab stock falls"),
        ("Rocket Lab upgraded at Morgan Stanley", "Rocket Lab downgraded at Morgan Stanley"),
        ("Should you buy Rocket Lab stock?", "Should you sell Rocket Lab stock?"),
        ("Rocket Lab Q1 results beat estimates", "Rocket Lab Q2 results beat estimates"),
        ("Rocket Lab wins $100M contract", "Rocket Lab wins $50M contract"),
        ("Rocket Lab (RKLB)", "Rocket Lab stock jumps on launch news"),
        ("Rocket Lab Neutron update", "Rocket Lab Neutron launch succeeds"),
        ("Rocket Lab wins NASA contract", "Rocket Lab loses NASA contract"),
        ("Rocket Lab Electron launch succeeds", "Rocket Lab Electron launch fails"),
        ("Rocket Lab hits record high", "Rocket Lab hits record low"),
        (
            "Rocket Lab will launch Neutron this year",
            "Rocket Lab will not launch Neutron this year",
        ),
        ("Rocket Lab wins launch deal with NASA", "Rocket Lab wins no launch deal with NASA"),
        ("Rocket Lab beats earnings estimates", "Rocket Lab misses earnings estimates"),
        ("Rocket Lab raises full-year guidance", "Rocket Lab cuts full-year guidance"),
        ("Rocket Lab shares rise on Neutron news", "Rocket Lab shares fall on Neutron news"),
    ],
)
def test_cluster_stories_opposite_or_different_stories_do_not_group(a: str, b: str) -> None:
    assert _groups([a, b]) == [[0], [1]]


def test_cluster_stories_contains_rule_needs_three_tokens_in_the_smaller_title() -> None:
    long = "Apple unveils iPhone lineup with faster chips and better cameras at big event"
    short = "Apple unveils iPhone lineup"

    assert _groups([long, short]) == [[0, 1]]
    assert _groups([long, "Apple unveils"]) == [[0], [1]]


def test_cluster_stories_same_story_on_different_days_is_not_grouped() -> None:
    titles = ["Rocket Lab delays Neutron launch to 2027", "Rocket Lab delays Neutron debut to 2027"]

    assert _groups(titles, [DAY, NEXT_DAY]) == [[0], [1]]


def test_cluster_stories_keeps_input_order_with_newest_as_main() -> None:
    groups = _groups(
        [
            "Rocket Lab wins Space Force contract",
            "Rocket Lab delays Neutron launch to 2027",
            "Unrelated Fed rate decision looms",
            "Rocket Lab delays Neutron debut to 2027",
        ]
    )

    assert groups == [[0], [1, 3], [2]]


def test_cluster_stories_empty_token_sets_never_group() -> None:
    assert _groups(["the", "the"]) == [[0], [1]]


NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)  # noqa: UP017
SINCE = NOW - timedelta(days=182)


def test_month_window_returns_exchange_local_bounds_in_utc() -> None:
    start, end = month_window("2026-09", NY, NOW, SINCE)

    assert start == datetime(2026, 9, 1, 4, tzinfo=timezone.utc)  # noqa: UP017
    assert end == datetime(2026, 10, 1, 4, tzinfo=timezone.utc)  # noqa: UP017


def test_month_window_clips_the_start_to_the_window() -> None:
    start, _ = month_window("2026-04", NY, NOW, SINCE)

    assert start == SINCE


@pytest.mark.parametrize(
    "month",
    [
        "2026-9",
        "2026-13",
        "٢٠٢٦-١٠",  # noqa: RUF001
        "2026-10-01",
        "0000-01",
        "9999-12",
        "2026-03",
        "2026-11",
    ],
)
def test_month_window_rejects_malformed_and_out_of_window_months(month: str) -> None:
    with pytest.raises(InvalidMonthError):
        month_window(month, NY, NOW, SINCE)


def test_cluster_stories_delay_synonyms_fold_to_one_word() -> None:
    titles = ["Rocket Lab Neutron launch pushed to 2027", "Rocket Lab Neutron launch delayed 2027"]

    assert _groups(titles) == [[0, 1]]


def test_cluster_stories_plural_forms_group_but_short_words_and_ss_endings_are_kept() -> None:
    assert _groups(["alpha beta share", "alpha beta shares"]) == [[0, 1]]
    # "loss" must not become "los": that would give 3 shared tokens and merge these.
    assert _groups(["alpha beta loss", "alpha beta los"]) == [[0], [1]]
