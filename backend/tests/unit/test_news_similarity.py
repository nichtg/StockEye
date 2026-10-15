"""Near-duplicate headline grouping: pure rules, no I/O."""

from datetime import date

from app.domain.news import cluster_stories, title_tokens

DAY = date(2026, 10, 2)
NEXT_DAY = date(2026, 10, 1)

NEUTRON_A = "Rocket Lab delays Neutron debut to 2027"
NEUTRON_B = "Rocket Lab's Neutron rocket delayed to 2027"
NEUTRON_C = "Neutron launch pushed to 2027, Rocket Lab says"
CONTRACT = "Rocket Lab wins $200M Space Force contract"


def _groups(titles: list[str], days: list[date] | None = None) -> list[list[int]]:
    tokens = [title_tokens(t, {"rklb"}) for t in titles]
    return cluster_stories(days or [DAY] * len(titles), tokens)


def test_title_tokens_lowercases_strips_punctuation_stop_words_and_ignored() -> None:
    tokens = title_tokens("The RKLB Stock, Is Up! (again)", {"rklb"})

    assert tokens == frozenset({"stock", "up", "again"})


def test_cluster_stories_neutron_delay_from_three_outlets_groups() -> None:
    groups = _groups([NEUTRON_A, NEUTRON_B, NEUTRON_C])

    assert groups == [[0, 1, 2]]


def test_cluster_stories_different_stories_about_one_company_stay_apart() -> None:
    groups = _groups([NEUTRON_A, CONTRACT])

    assert groups == [[0], [1]]


def test_cluster_stories_containment_rule_groups_a_short_title_inside_a_long_one() -> None:
    long = "Apple unveils new iPhone lineup with faster chips and better cameras at event"
    short = "Apple unveils iPhone lineup"  # Jaccard is low, but all its tokens are in the long one

    assert _groups([long, short]) == [[0, 1]]


def test_cluster_stories_same_story_on_different_days_is_not_grouped() -> None:
    groups = _groups([NEUTRON_A, NEUTRON_B], [DAY, NEXT_DAY])

    assert groups == [[0], [1]]


def test_cluster_stories_keeps_input_order_with_newest_as_main() -> None:
    groups = _groups([CONTRACT, NEUTRON_A, "Unrelated Fed news", NEUTRON_B])

    assert groups == [[0], [1, 3], [2]]


def test_cluster_stories_titles_differing_only_by_a_number_stay_apart() -> None:
    assert _groups(["headline 1", "headline 2"]) == [[0], [1]]


def test_cluster_stories_empty_token_sets_never_group() -> None:
    assert _groups(["the", "the"]) == [[0], [1]]
