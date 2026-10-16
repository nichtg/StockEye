"""Ingest-time near-duplicate folding: pure rules, no I/O."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.domain.news import Story, fold_near_duplicates

NY = ZoneInfo("America/New_York")
IGNORE = {"rklb", "rocket", "lab"}
NEUTRON = "Rocket Lab delays Neutron launch to 2027"
NEUTRON_ALT = "Rocket Lab's Neutron rocket delayed to 2027"


def _story(key: str, title: str, hour: int, day: int = 2) -> Story:
    return Story(key, title, datetime(2026, 10, day, hour, tzinfo=UTC))


def test_fold_new_story_duplicating_a_stored_one_points_at_the_stored_article() -> None:
    stored = [_story("s", NEUTRON, 15)]
    new = [_story("n", NEUTRON_ALT, 14)]  # published earlier, but the stored one stays main

    assert fold_near_duplicates(new, stored, NY, IGNORE) == {"n": "s"}


def test_fold_within_a_batch_the_earliest_published_stays_main() -> None:
    new = [
        _story("late", NEUTRON_ALT, 18),
        _story("early", NEUTRON, 13),
        _story("mid", "Rocket Lab delays Neutron debut to 2027", 15),
    ]

    assert fold_near_duplicates(new, [], NY, IGNORE) == {"late": "early", "mid": "early"}


def test_fold_same_story_on_another_exchange_local_day_is_not_folded() -> None:
    # 03:00 UTC on 2 Oct is still 1 Oct in New York.
    stored = [_story("s", NEUTRON, 3, day=2)]
    new = [_story("n", NEUTRON_ALT, 15, day=2)]

    assert fold_near_duplicates(new, stored, NY, IGNORE) == {}
    assert fold_near_duplicates(new, stored, ZoneInfo("UTC"), IGNORE) == {"n": "s"}


def test_fold_opposed_stories_never_merge() -> None:
    stored = [_story("s", "Rocket Lab Electron launch succeeds today", 15)]
    new = [_story("n", "Rocket Lab Electron launch fails today", 16)]

    assert fold_near_duplicates(new, stored, NY, IGNORE) == {}


def test_fold_loosely_worded_rewrites_stay_apart_for_precision() -> None:
    new = [
        _story(
            "a", "Rocket Lab Updates Neutron Development Schedule, Targets Inaugural Launch", 13
        ),
        _story(
            "b", "Rocket Lab Announces Delay of Neutron Rocket's Maiden Launch to Next Year", 14
        ),
    ]

    assert fold_near_duplicates(new, [], NY, IGNORE) == {}


def test_fold_story_already_stored_is_not_a_duplicate_of_itself() -> None:
    stored = [_story("s", NEUTRON, 15)]
    new = [_story("s", NEUTRON, 15)]  # a re-fetch of the stored article

    assert fold_near_duplicates(new, stored, NY, IGNORE) == {}


def test_fold_repeated_key_in_one_batch_is_left_to_the_upsert() -> None:
    new = [_story("k", NEUTRON, 13), _story("k", NEUTRON, 13)]

    assert fold_near_duplicates(new, [], NY, IGNORE) == {}


def test_fold_outcome_does_not_depend_on_the_order_of_stored_stories() -> None:
    older = _story("a-older", NEUTRON, 12)
    newer = _story("b-newer", "Rocket Lab delays Neutron debut to 2027", 14)
    new = [_story("n", NEUTRON_ALT, 16)]

    forward = fold_near_duplicates(new, [older, newer], NY, IGNORE)
    backward = fold_near_duplicates(new, [newer, older], NY, IGNORE)

    assert forward == backward == {"n": "a-older"}  # the earliest stored story is the head
