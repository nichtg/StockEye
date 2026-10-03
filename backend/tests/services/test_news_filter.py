import pytest

from app.repositories.news import dedupe_key
from app.services.news import core_name, is_relevant


@pytest.mark.parametrize(
    ("company", "expected"),
    [
        ("DBS Group Holdings Ltd", "DBS"),
        ("Apple Inc.", "Apple"),
        ("Microsoft Corporation", "Microsoft"),
        ("Koninklijke Philips N.V.", "Koninklijke Philips"),
        ("Holdings Group", "Holdings"),
        ("Procter & Gamble Co", "Procter & Gamble"),
    ],
)
def test_core_name_strips_legal_suffixes(company: str, expected: str) -> None:
    assert core_name(company) == expected


def test_is_relevant_matches_core_name_case_insensitively() -> None:
    assert is_relevant("AAPL", "Apple Inc.", "APPLE unveils a new phone", None)


def test_is_relevant_matches_summary_too() -> None:
    assert is_relevant("AAPL", "Apple Inc.", "Tech roundup", "Shares of Apple rose today")


def test_is_relevant_rejects_unrelated_article() -> None:
    assert not is_relevant("AAPL", "Apple Inc.", "Orchard harvest hits a record", "Pineapple crop")


def test_is_relevant_core_name_must_be_a_whole_word() -> None:
    assert not is_relevant("D05.SI", "DBS Group Holdings Ltd", "Adbsomething surges", None)
    assert is_relevant("D05.SI", "DBS Group Holdings Ltd", "DBS posts record profit", None)


def test_is_relevant_matches_ticker_root_as_a_word() -> None:
    assert is_relevant("MSFT", "Something Else Ltd", "Why MSFT jumped today", None)


def test_is_relevant_ignores_short_ticker_roots() -> None:
    assert not is_relevant("AB", "Zzz Holdings", "AB testing explained", None)


def test_dedupe_key_ignores_case_punctuation_and_spacing() -> None:
    a = dedupe_key("Apple Beats Estimates!", "Example Wire")
    b = dedupe_key("apple  beats estimates", "EXAMPLE WIRE")

    assert a == b


def test_dedupe_key_differs_by_source() -> None:
    assert dedupe_key("Same title", "Reuters") != dedupe_key("Same title", "Bloomberg")
