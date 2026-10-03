"""The JWT secret has no default: weak or placeholder secrets stop the app from starting."""

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.config import MIN_JWT_SECRET_LENGTH, Settings

STRONG = "k3Y-" + "x" * 40


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("STOCKEYE_JWT_SECRET", raising=False)
    monkeypatch.chdir(tmp_path)  # no stray .env


@pytest.mark.parametrize("environment", ["dev", "prod"])
def test_settings_missing_secret_outside_test_refuses_to_start(environment: str) -> None:
    with pytest.raises(ValidationError, match="STOCKEYE_JWT_SECRET"):
        Settings.model_validate({"environment": environment})


@pytest.mark.parametrize(
    "secret",
    [
        "replace-me-with-a-long-random-string",
        "changeme" + "0" * 30,
        "dev-only-insecure-secret-change-me-0123456789",
        "SECRET",
    ],
)
def test_settings_placeholder_secret_is_rejected(secret: str) -> None:
    with pytest.raises(ValidationError, match="placeholder"):
        Settings.model_validate({"environment": "prod", "jwt_secret": secret})


def test_settings_short_secret_is_rejected() -> None:
    with pytest.raises(ValidationError, match=str(MIN_JWT_SECRET_LENGTH)):
        Settings.model_validate({"environment": "prod", "jwt_secret": "a" * 31})


def test_settings_strong_secret_is_accepted_in_prod() -> None:
    settings = Settings.model_validate({"environment": "prod", "jwt_secret": STRONG})

    assert settings.jwt_secret.get_secret_value() == STRONG


def test_settings_test_environment_generates_a_random_secret_per_instance() -> None:
    first, second = Settings(environment="test"), Settings(environment="test")

    secret = first.jwt_secret.get_secret_value()
    assert len(secret) >= MIN_JWT_SECRET_LENGTH
    assert secret != second.jwt_secret.get_secret_value()


def test_settings_test_environment_keeps_an_explicit_secret() -> None:
    settings = Settings(environment="test", jwt_secret=SecretStr(STRONG))

    assert settings.jwt_secret.get_secret_value() == STRONG


def test_settings_secret_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKEYE_JWT_SECRET", STRONG)

    assert Settings().jwt_secret.get_secret_value() == STRONG
