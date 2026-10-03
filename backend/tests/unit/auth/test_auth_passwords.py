import pytest

from app.auth.passwords import (
    PasswordPolicyError,
    hash_password,
    needs_rehash,
    validate_password,
    verify_dummy,
    verify_password,
)


def test_hash_password_then_verify_correct_password_returns_true() -> None:
    hashed = hash_password("a-long-enough-password")

    assert hashed.startswith("$argon2id$")
    assert verify_password("a-long-enough-password", hashed)


def test_verify_password_wrong_password_returns_false_without_raising() -> None:
    hashed = hash_password("a-long-enough-password")

    assert verify_password("another-password-here", hashed) is False


def test_verify_password_malformed_hash_returns_false() -> None:
    assert verify_password("whatever-password-1", "not-a-hash") is False


def test_needs_rehash_fresh_hash_is_false() -> None:
    assert needs_rehash(hash_password("a-long-enough-password")) is False


@pytest.mark.parametrize(
    ("password", "email", "fragment"),
    [
        ("short", None, "at least 12"),
        ("x" * 129, None, "at most 128"),
        (" " * 20, None, "whitespace"),
        ("user@example.com", "user@example.com", "email"),
        ("USER@example.com", "user@example.com", "email"),
    ],
)
def test_validate_password_violation_raises_plain_english(
    password: str, email: str | None, fragment: str
) -> None:
    with pytest.raises(PasswordPolicyError, match=fragment):
        validate_password(password, email)


@pytest.mark.parametrize("password", ["x" * 12, "y" * 128])
def test_validate_password_boundary_lengths_are_accepted(password: str) -> None:
    validate_password(password, "someone@example.com")


def test_verify_dummy_accepts_any_password_without_raising() -> None:
    verify_dummy("whatever-password-1")
