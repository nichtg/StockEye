"""Application settings, loaded once from env vars (prefix ``STOCKEYE_``) or ``.env``."""

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from limits import RateLimitItem, parse
from pydantic import BaseModel, BeforeValidator, ConfigDict, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_JWT_SECRET_LENGTH = 32
# Values people copy from docs and examples; a deployment that still has one is unprotected.
_PLACEHOLDER_PREFIXES = ("replace-me", "changeme", "change-me", "dev-only-insecure")
_PLACEHOLDER_SECRETS = frozenset({"secret", "password", "jwt-secret", "your-secret-here"})


class ProviderLimits(BaseModel):
    """Self-imposed call budgets per provider. Free tiers are respected with headroom."""

    per_minute: int
    per_day: int


def _parse_rate(value: object) -> object:
    """A ``limits`` rate string such as "20/minute" becomes a rate item; a bad one fails startup."""
    return parse(value) if isinstance(value, str) else value


type Rate = Annotated[RateLimitItem, BeforeValidator(_parse_rate)]


type Bucket = Literal["search", "stock", "macro", "overview", "watchlist", "auth"]


class RateLimits(BaseModel):
    """Request budgets, each a ``limits`` rate string such as "20/minute" (see app.api.limits).

    The data endpoints are budgeted per signed-in user and several routes may share one bucket;
    ``auth`` is budgeted per client address, since nobody is signed in yet.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    search: Rate = parse("60/minute")
    stock: Rate = parse("120/minute")  # the quote, chart and technical endpoints share it
    macro: Rate = parse("20/minute")
    overview: Rate = parse("20/minute")
    watchlist: Rate = parse("30/minute")
    auth: Rate = parse("10/minute")

    def for_bucket(self, bucket: Bucket) -> Rate:
        return {
            "search": self.search,
            "stock": self.stock,
            "macro": self.macro,
            "overview": self.overview,
            "watchlist": self.watchlist,
            "auth": self.auth,
        }[bucket]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STOCKEYE_",
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    environment: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"

    mongodb_uri: str = "mongodb://127.0.0.1:27017"
    mongodb_db: str = "stockeye"

    # No default: an unset secret is a startup error everywhere except the ``test`` environment.
    jwt_secret: SecretStr = SecretStr("")
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14
    cookie_secure: bool = True
    cors_origins: list[str] = ["http://localhost:5173"]
    login_max_failures: int = 5
    login_lockout_minutes: int = 15

    finnhub_api_key: SecretStr | None = None
    alphavantage_api_key: SecretStr | None = None
    marketaux_api_key: SecretStr | None = None

    provider_limits: dict[str, ProviderLimits] = {
        "yahoo": ProviderLimits(per_minute=60, per_day=4000),
        "google_news": ProviderLimits(per_minute=20, per_day=1500),
        "finnhub": ProviderLimits(per_minute=50, per_day=40000),
        "alphavantage": ProviderLimits(per_minute=5, per_day=25),
        "marketaux": ProviderLimits(per_minute=10, per_day=100),
    }
    quota_warning_ratio: float = 0.8

    rate_limits: RateLimits = RateLimits()
    # Symbols never ingested before that one user may trigger a news backfill for, per UTC day.
    max_new_symbols_per_user_per_day: int = 10
    max_concurrent_ingestions: int = 2

    finbert_model_dir: Path = Path("models/finbert")
    scheduler_enabled: bool = True

    @model_validator(mode="after")
    def _require_strong_jwt_secret(self) -> "Settings":
        secret = self.jwt_secret.get_secret_value()
        if self.environment == "test" and not secret:
            # Tests never share tokens across processes, so a throwaway key per instance is right.
            self.jwt_secret = SecretStr(secrets.token_urlsafe(48))
            return self
        lowered = secret.strip().lower()
        if lowered.startswith(_PLACEHOLDER_PREFIXES) or lowered in _PLACEHOLDER_SECRETS:
            raise ValueError("STOCKEYE_JWT_SECRET is still a placeholder; generate a random one")
        if len(secret) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(
                f"STOCKEYE_JWT_SECRET must be set to at least {MIN_JWT_SECRET_LENGTH} characters"
                ' (python -c "import secrets; print(secrets.token_urlsafe(48))")'
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
