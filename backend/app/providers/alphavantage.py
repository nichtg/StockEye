"""Alpha Vantage NEWS_SENTIMENT. Only the news fields are used; its sentiment is ignored."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel

from app.providers.collect import collect_items
from app.providers.errors import ProviderDataError, RateLimitedError
from app.providers.http import get_json
from app.providers.models import NewsItem, NewsQuery

URL = "https://www.alphavantage.co/query"
_EASTERN = ZoneInfo("America/New_York")
_STAMP = "%Y%m%dT%H%M%S"


class _Article(BaseModel):
    title: str
    summary: str | None = None
    source: str
    url: str
    time_published: str


class AlphaVantageNews:
    name = "alphavantage"

    def __init__(self, client: httpx.AsyncClient, api_key: str) -> None:
        self._client = client
        self._key = api_key

    async def fetch(self, query: NewsQuery) -> list[NewsItem]:
        if query.exchange == "SGX":
            return []  # NEWS_SENTIMENT tickers are US-listed only
        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": query.symbol,
            "time_from": query.start.strftime("%Y%m%dT%H%M"),
            "time_to": query.end.strftime("%Y%m%dT%H%M"),
            "limit": 1000,
            "apikey": self._key,
        }
        payload = await get_json(self._client, URL, provider=self.name, params=params)
        if not isinstance(payload, dict):
            raise ProviderDataError(self.name, "expected a JSON object")
        # Alpha Vantage signals throttling inside a 200 response body.
        if "Note" in payload or "Information" in payload:
            raise RateLimitedError(self.name, retry_after=None)
        feed = payload.get("feed")
        if feed is None:
            return []  # no articles in the window
        if not isinstance(feed, list):
            raise ProviderDataError(self.name, "feed is not a list")
        return collect_items(self.name, feed, self._to_item)

    def _to_item(self, raw: object) -> NewsItem:
        art = _Article.model_validate(raw)
        published = (
            datetime.strptime(art.time_published, _STAMP).replace(tzinfo=_EASTERN).astimezone(UTC)
        )
        return NewsItem.model_validate(
            {
                "url": art.url,
                "title": art.title,
                "summary": art.summary or None,
                "source": art.source,
                "published_at": published,
                "provider": self.name,
            }
        )
