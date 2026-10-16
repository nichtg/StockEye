"""Company-name helpers for the news pipeline."""

from app.domain.news import core_name, ignore_tokens, shared_words


def test_core_name_strips_trailing_legal_suffixes() -> None:
    assert core_name("DBS Group Holdings Ltd") == "DBS"
    assert core_name("Inc") == "Inc"  # a name that is only a suffix is kept whole


def test_ignore_tokens_holds_ticker_parts_and_core_name() -> None:
    assert ignore_tokens("D05.SI", "DBS Group Holdings Ltd") == {"d05", "si", "dbs"}


def test_shared_words_finds_the_words_most_headlines_carry() -> None:
    titles = [f"Apple news item {n}" for n in range(12)] + ["Apple wins big"] * 2

    assert {"apple"} <= shared_words(titles)
    assert "wins" not in shared_words(titles)


def test_shared_words_with_too_few_titles_ignores_nothing() -> None:
    assert shared_words(["Apple one", "Apple two"]) == set()
