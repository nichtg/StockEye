"""Password hashing (argon2id) and the password policy.

Hashing and verifying cost tens of milliseconds of CPU, so they are coroutines that run on a
worker thread: a burst of logins must not freeze every other request on the event loop.
"""

import asyncio
import os
import re
import weakref
from functools import cache
from importlib.resources import files

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_LENGTH = 12
MAX_LENGTH = 128

_hasher = PasswordHasher()  # library defaults are argon2id with current RFC 9106 parameters
# Verified against when an email is unknown so login timing does not reveal which emails exist.
_DUMMY_HASH = _hasher.hash("stockeye-dummy-password-for-timing")
# argon2 is memory-hard (tens of MiB per call), so cap parallel hashes at the core count; extra
# logins queue here instead of exhausting memory or the default thread pool. A semaphore belongs
# to the event loop it first waits on, so each running loop gets its own.
_slots: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
    weakref.WeakKeyDictionary()
)

# Trailing digits and punctuation: "letmein2024!" is "letmein" with a suffix attackers try first.
_SUFFIX = re.compile(r"[\d\W_]+$")


class PasswordPolicyError(ValueError):
    """The password violates the policy; the message is safe to show to the user."""


def _slot() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    if loop not in _slots:
        _slots[loop] = asyncio.Semaphore(os.cpu_count() or 1)
    return _slots[loop]


@cache
def _common_passwords() -> frozenset[str]:
    text = files("app.auth").joinpath("common_passwords.txt").read_text(encoding="utf-8")
    return frozenset(
        line.strip().lower() for line in text.splitlines() if line and not line.startswith("#")
    )


def _is_common(password: str) -> bool:
    lowered = password.strip().lower()
    common = _common_passwords()
    return lowered in common or _SUFFIX.sub("", lowered) in common


def validate_password(password: str, email: str | None = None) -> None:
    """Raise ``PasswordPolicyError`` unless it is 12-128 chars, not blank, not the email and
    not a well-known password (exactly, or with digits/symbols appended)."""
    if len(password) < MIN_LENGTH:
        raise PasswordPolicyError(f"Password must be at least {MIN_LENGTH} characters long.")
    if len(password) > MAX_LENGTH:
        raise PasswordPolicyError(f"Password must be at most {MAX_LENGTH} characters long.")
    if not password.strip():
        raise PasswordPolicyError("Password must not consist only of whitespace.")
    if email is not None and password.strip().lower() == email.strip().lower():
        raise PasswordPolicyError("Password must not be the same as your email address.")
    if _is_common(password):
        raise PasswordPolicyError(
            "That password is too common. Please choose a less guessable one."
        )


async def hash_password(password: str) -> str:
    async with _slot():
        return await asyncio.to_thread(_hasher.hash, password)


async def verify_password(password: str, password_hash: str) -> bool:
    """True when the password matches. Never raises on a mismatch or a malformed hash."""
    async with _slot():
        return await asyncio.to_thread(_verify, password, password_hash)


def _verify(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


async def verify_dummy(password: str) -> None:
    """Spend a real verification's CPU so unknown-email logins take as long as wrong passwords."""
    await verify_password(password, _DUMMY_HASH)


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)
