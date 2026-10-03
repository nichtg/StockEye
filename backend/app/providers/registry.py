"""Wiring: which news providers are active, and which are configured (for the admin panel)."""

import httpx

from app.config import Settings
from app.providers.alphavantage import AlphaVantageNews
from app.providers.base import NewsProvider
from app.providers.finnhub import FinnhubNews
from app.providers.google_news import GoogleNewsRss
from app.providers.marketaux import MarketauxNews


def build_news_providers(settings: Settings, client: httpx.AsyncClient) -> list[NewsProvider]:
    """Keyed vendors first (richer data), Google News RSS last as the always-on fallback."""
    providers: list[NewsProvider] = []
    if settings.finnhub_api_key:
        providers.append(FinnhubNews(client, settings.finnhub_api_key.get_secret_value()))
    if settings.marketaux_api_key:
        providers.append(MarketauxNews(client, settings.marketaux_api_key.get_secret_value()))
    if settings.alphavantage_api_key:
        providers.append(AlphaVantageNews(client, settings.alphavantage_api_key.get_secret_value()))
    providers.append(GoogleNewsRss(client))
    return providers


def configured_providers(settings: Settings) -> dict[str, bool]:
    return {
        "yahoo": True,
        "google_news": True,
        "finnhub": settings.finnhub_api_key is not None,
        "marketaux": settings.marketaux_api_key is not None,
        "alphavantage": settings.alphavantage_api_key is not None,
    }
