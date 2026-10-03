"""Google News RSS search. No API key; the only provider that can reach far back for backfill."""

import calendar
import html
import re
from datetime import UTC, datetime
from itertools import pairwise

import feedparser
import httpx
from pydantic import ValidationError

from app.logging_setup import get_logger
from app.providers.http import get_text
from app.providers.models import NewsItem, NewsQuery

log = get_logger(__name__)
URL = "https://news.google.com/rss/search"
_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


def _strip_html(raw: str) -> str:
    return _SPACES.sub(" ", html.unescape(_TAGS.sub(" ", raw))).strip()


def _shift_months(moment: datetime, months: int) -> datetime:
    """Move ``moment`` back by whole calendar months, clamping the day to the month length."""
    index = moment.year * 12 + (moment.month - 1) - months
    year, month = divmod(index, 12)
    month += 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def monthly_windows(end: datetime, months: int = 24) -> list[tuple[datetime, datetime]]:
    """Consecutive one-month windows ending at ``end``, oldest first.

    Google News caps each RSS response at about 100 items, so history is fetched in slices.
    """
    edges = [_shift_months(end, n) for n in range(months, -1, -1)]
    return list(pairwise(edges))


def _split_title(title: str) -> tuple[str, str] | None:
    """'Headline - Publisher' -> (headline, publisher), splitting on the last separator."""
    head, sep, publisher = title.rpartition(" - ")
    if not sep or not head or not publisher:
        return None
    return head.strip(), publisher.strip()


class GoogleNewsRss:
    name = "google_news"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def fetch(self, query: NewsQuery) -> list[NewsItem]:
        country = "SG" if query.symbol.upper().endswith(".SI") else "US"
        q = (
            f'"{query.company_name}" after:{query.start.date().isoformat()} '
            f"before:{query.end.date().isoformat()}"
        )
        params = {"q": q, "hl": f"en-{country}", "gl": country, "ceid": f"{country}:en"}
        text = await get_text(self._client, URL, provider=self.name, params=params)
        return self._parse(text)

    def _parse(self, text: str) -> list[NewsItem]:
        feed = feedparser.parse(text)
        items: list[NewsItem] = []
        for entry in feed.entries:
            try:
                raw_title = str(entry.get("title", "")).strip()
                split = _split_title(raw_title)
                title, source = split if split else (raw_title, str(_publisher(entry)))
                summary: str | None = _strip_html(str(entry.get("summary", ""))) or None
                if summary is not None and (
                    summary == title or (title in summary and len(summary) <= len(raw_title) + 8)
                ):
                    summary = None  # Google's description just repeats the headline
                parsed = entry.get("published_parsed")
                if not parsed or not title or not source:
                    raise ValueError("missing title, source or date")  # noqa: TRY301
                published = datetime(*parsed[:6]).replace(tzinfo=UTC)  # noqa: DTZ001 - tz set here
                items.append(
                    NewsItem.model_validate(
                        {
                            "url": entry.get("link", ""),
                            "title": title,
                            "summary": summary,
                            "source": source,
                            "published_at": published,
                            "provider": self.name,
                        }
                    )
                )
            except (ValidationError, ValueError, TypeError):
                log.debug("provider_item_skipped", provider=self.name)
        return items


def _publisher(entry: feedparser.FeedParserDict) -> str:
    source = entry.get("source")
    return str(source.get("title", "")) if source else ""
