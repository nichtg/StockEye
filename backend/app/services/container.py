"""The services container: built once in the app lifespan, stored on ``app.state.services``.

``create_app`` accepts a ``ServicesFactory`` so tests build the whole app around fake providers
without monkeypatching globals. A factory (rather than a dependency override) keeps the lifespan
the single owner of construction and shutdown, and lets a test replace *everything* (providers,
scorer, clock) in one place while the routers stay untouched.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import Depends, Request

from app.config import Settings
from app.db import Database
from app.providers.registry import build_news_providers
from app.providers.resilience import ProviderGuard
from app.providers.yahoo import YahooMarketData
from app.repositories.quotas import QuotaLedger
from app.sentiment.finbert_onnx import FinBertOnnxScorer
from app.services.analysis import AnalysisService
from app.services.market_data import MarketDataService
from app.services.news import NewsService


@dataclass
class Services:
    market: MarketDataService
    news: NewsService
    analysis: AnalysisService
    guard: ProviderGuard
    http: httpx.AsyncClient | None = None

    async def aclose(self) -> None:
        """Stop background ingestion, then close the HTTP client."""
        await self.news.shutdown()
        if self.http is not None:
            await self.http.aclose()


type ServicesFactory = Callable[[Settings, Database], Awaitable[Services]]


async def build_services(settings: Settings, db: Database) -> Services:
    """Production wiring: Yahoo, the configured news providers, FinBERT, and the quota ledger."""
    http = httpx.AsyncClient(
        timeout=httpx.Timeout(15.0),
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; StockEye/0.1)"},
    )
    guard = ProviderGuard(
        QuotaLedger(db, settings.quota_warning_ratio),
        settings.provider_limits,
        settings.quota_warning_ratio,
    )
    market = MarketDataService(db, YahooMarketData(), guard)
    news = NewsService(
        db,
        build_news_providers(settings, http),
        guard,
        FinBertOnnxScorer(settings.finbert_model_dir),
    )
    return Services(market, news, AnalysisService(db, market, news), guard, http)


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


ServicesDep = Annotated[Services, Depends(get_services)]
