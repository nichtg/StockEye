"""Marketaux news."""

from datetime import datetime

import httpx
from pydantic import BaseModel, ValidationError

from app.providers.collect import collect_items
from app.providers.errors import ProviderDataError
from app.providers.http import get_json
from app.providers.models import Exchange, NewsItem, NewsQuery

URL = "https://api.marketaux.com/v1/news/all"


class _Article(BaseModel):
    title: str
    description: str | None = None
    source: str
    url: str
    published_at: datetime


class _Response(BaseModel):
    data: list[object]


class MarketauxNews:
    name = "marketaux"
    exchanges: frozenset[Exchange] = frozenset({"US", "SGX"})

    def __init__(self, client: httpx.AsyncClient, api_key: str) -> None:
        self._client = client
        self._key = api_key

    async def fetch(self, query: NewsQuery) -> list[NewsItem]:
        params = {
            "symbols": query.symbol,
            "published_after": query.start.strftime("%Y-%m-%dT%H:%M"),
            "published_before": query.end.strftime("%Y-%m-%dT%H:%M"),
            "language": "en",
            "api_token": self._key,
        }
        payload = await get_json(self._client, URL, provider=self.name, params=params)
        try:
            rows = _Response.model_validate(payload).data
        except ValidationError as exc:
            raise ProviderDataError(self.name, "response has no data list") from exc
        return collect_items(self.name, rows, self._to_item)

    def _to_item(self, raw: object) -> NewsItem:
        art = _Article.model_validate(raw)
        return NewsItem.model_validate(
            {
                "url": art.url,
                "title": art.title,
                "summary": art.description or None,
                "source": art.source,
                "published_at": art.published_at,
                "provider": self.name,
            }
        )
