"""Password hashing (argon2id) and the password policy."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_LENGTH = 12
MAX_LENGTH = 128

_hasher = PasswordHasher()  # library defaults are argon2id with current RFC 9106 parameters
# Verified against when an email is unknown so login timing does not reveal which emails exist.
_DUMMY_HASH = _hasher.hash("stockeye-dummy-password-for-timing")


class PasswordPolicyError(ValueError):
    """The password violates the policy; the message is safe to show to the user."""


def validate_password(password: str, email: str | None = None) -> None:
    """Raise ``PasswordPolicyError`` unless it is 12-128 chars, not blank and not the email."""
    if len(password) < MIN_LENGTH:
        raise PasswordPolicyError(f"Password must be at least {MIN_LENGTH} characters long.")
    if len(password) > MAX_LENGTH:
        raise PasswordPolicyError(f"Password must be at most {MAX_LENGTH} characters long.")
    if not password.strip():
        raise PasswordPolicyError("Password must not consist only of whitespace.")
    if email is not None and password.strip().lower() == email.strip().lower():
        raise PasswordPolicyError("Password must not be the same as your email address.")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """True when the password matches. Never raises on a mismatch or a malformed hash."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def verify_dummy(password: str) -> None:
    """Spend a real verification's CPU so unknown-email logins take as long as wrong passwords."""
    verify_password(password, _DUMMY_HASH)


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)
