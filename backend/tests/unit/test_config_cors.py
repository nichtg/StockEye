"""Settings validation of the CORS origin list."""

import pytest
from pydantic import ValidationError

from app.config import Settings


def _settings(origins: list[str]) -> Settings:
    return Settings(environment="test", cors_origins=origins)


@pytest.mark.parametrize(
    "origin",
    ["http://localhost:5173", "https://nichtg.github.io", "https://app.example.com:8443"],
)
def test_cors_origins_exact_scheme_host_port_is_accepted(origin: str) -> None:
    assert _settings([origin]).cors_origins == [origin]


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "null",
        "",
        "https://example.com/",
        "https://example.com/app",
        "example.com",
        "ftp://example.com",
        "https://*.example.com",
        "https://example.com?x=1",
        "https://user@example.com",
        "https://example.com:port",
    ],
)
def test_cors_origins_wildcards_paths_and_odd_forms_are_rejected(origin: str) -> None:
    with pytest.raises(ValidationError, match="STOCKEYE_CORS_ORIGINS"):
        _settings(["https://ok.example.com", origin])
