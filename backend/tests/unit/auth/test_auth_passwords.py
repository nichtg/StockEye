import asyncio
from collections.abc import Callable
from importlib.resources import files

import pytest

from app.auth import passwords
from app.auth.passwords import (
    PasswordPolicyError,
    hash_password,
    needs_rehash,
    validate_password,
    verify_dummy,
    verify_password,
)


async def test_hash_password_then_verify_correct_password_returns_true() -> None:
    hashed = await hash_password("a-long-enough-password")

    assert hashed.startswith("$argon2id$")
    assert await verify_password("a-long-enough-password", hashed)


async def test_verify_password_wrong_password_returns_false_without_raising() -> None:
    hashed = await hash_password("a-long-enough-password")

    assert await verify_password("another-password-here", hashed) is False


async def test_verify_password_malformed_hash_returns_false() -> None:
    assert await verify_password("whatever-password-1", "not-a-hash") is False


async def test_needs_rehash_fresh_hash_is_false() -> None:
    assert needs_rehash(await hash_password("a-long-enough-password")) is False


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


async def test_verify_dummy_accepts_any_password_without_raising() -> None:
    await verify_dummy("whatever-password-1")


@pytest.mark.parametrize(
    "password",
    ["unbelievable", "Unbelievable", "  unbelievable  ", "unbelievable2024!", "motherfucker99"],
)
def test_validate_password_common_password_is_rejected_with_plain_message(password: str) -> None:
    with pytest.raises(PasswordPolicyError, match="too common"):
        validate_password(password, "someone@example.com")


def test_validate_password_uncommon_passphrase_is_accepted() -> None:
    validate_password("correct-horse-battery-staple", "someone@example.com")


def test_common_password_list_is_bundled_with_its_license_notice() -> None:
    text = files("app.auth").joinpath("common_passwords.txt").read_text(encoding="utf-8")

    assert "MIT License" in text
    assert sum(1 for line in text.splitlines() if line and not line.startswith("#")) >= 10_000


async def test_hashing_and_verifying_run_on_a_worker_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    offloaded: list[str] = []
    real_to_thread = asyncio.to_thread

    async def spy(func: Callable[..., object], /, *args: object) -> object:
        offloaded.append(getattr(func, "__name__", "?"))
        return await real_to_thread(func, *args)

    monkeypatch.setattr(passwords.asyncio, "to_thread", spy)

    hashed = await hash_password("a-long-enough-password")
    await verify_password("a-long-enough-password", hashed)

    assert len(offloaded) == 2


async def test_hashing_does_not_block_the_event_loop() -> None:
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.001)
            ticks += 1

    task = asyncio.create_task(ticker())
    await asyncio.gather(*(hash_password("a-long-enough-password") for _ in range(8)))
    task.cancel()

    # Hashing inline would hold the loop for the whole batch: the ticker would never run.
    assert ticks >= 3


async def test_concurrent_hashes_are_capped_by_the_semaphore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    in_flight = peak = 0
    slots = asyncio.Semaphore(2)

    async def fake_to_thread(func: Callable[..., object], /, *args: object) -> object:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return "hash"

    monkeypatch.setattr(passwords, "_slot", lambda: slots)
    monkeypatch.setattr(passwords.asyncio, "to_thread", fake_to_thread)

    await asyncio.gather(*(hash_password("a-long-enough-password") for _ in range(6)))

    assert peak == 2
