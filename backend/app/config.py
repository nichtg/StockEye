"""Application settings, loaded once from env vars (prefix ``STOCKEYE_``) or ``.env``."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_JWT_SECRET = "dev-only-insecure-secret-change-me-0123456789"  # noqa: S105 - rejected in prod


class ProviderLimits(BaseModel):
    """Self-imposed call budgets per provider. Free tiers are respected with headroom."""

    per_minute: int
    per_day: int


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

    jwt_secret: SecretStr = SecretStr(_DEV_JWT_SECRET)
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

    finbert_model_dir: Path = Path("models/finbert")
    scheduler_enabled: bool = True

    @model_validator(mode="after")
    def _forbid_dev_secret_in_prod(self) -> "Settings":
        if self.environment == "prod" and self.jwt_secret.get_secret_value() == _DEV_JWT_SECRET:
            raise ValueError("STOCKEYE_JWT_SECRET must be set in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
