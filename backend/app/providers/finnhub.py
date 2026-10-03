"""Finnhub company news (US symbols only)."""

from datetime import UTC, datetime

import httpx
from pydantic import BaseModel, ValidationError

from app.logging_setup import get_logger
from app.providers.errors import ProviderDataError
from app.providers.http import get_json
from app.providers.models import NewsItem, NewsQuery

log = get_logger(__name__)
URL = "https://finnhub.io/api/v1/company-news"


class _Article(BaseModel):
    datetime: int
    headline: str
    summary: str = ""
    source: str
    url: str


class FinnhubNews:
    name = "finnhub"

    def __init__(self, client: httpx.AsyncClient, api_key: str) -> None:
        self._client = client
        self._key = api_key

    async def fetch(self, query: NewsQuery) -> list[NewsItem]:
        if query.symbol.upper().endswith(".SI"):
            return []  # Finnhub's free tier covers US companies only
        params = {
            "symbol": query.symbol,
            "from": query.start.date().isoformat(),
            "to": query.end.date().isoformat(),
            "token": self._key,
        }
        payload = await get_json(self._client, URL, provider=self.name, params=params)
        if not isinstance(payload, list):
            raise ProviderDataError(self.name, "expected a list of articles")
        items: list[NewsItem] = []
        for raw in payload:
            try:
                art = _Article.model_validate(raw)
                items.append(
                    NewsItem.model_validate(
                        {
                            "url": art.url,
                            "title": art.headline,
                            "summary": art.summary or None,
                            "source": art.source,
                            "published_at": datetime.fromtimestamp(art.datetime, UTC),
                            "provider": self.name,
                        }
                    )
                )
            except (ValidationError, OverflowError, OSError, ValueError):
                log.debug("provider_item_skipped", provider=self.name)
        return items
