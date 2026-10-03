"""Shared row-to-item loop for the news adapters."""

from collections.abc import Callable, Iterable

from app.logging_setup import get_logger
from app.providers.models import NewsItem

log = get_logger(__name__)

# What a malformed vendor row raises: pydantic's ValidationError is a ValueError, and the
# timestamp conversions add OverflowError/OSError.
_BAD_ROW = (ValueError, TypeError, OverflowError, OSError)


def collect_items[Row](
    provider: str, rows: Iterable[Row], to_item: Callable[[Row], NewsItem]
) -> list[NewsItem]:
    """Convert each vendor row with ``to_item``, dropping rows that do not validate.

    One bad article must not discard the rest of a response, so a malformed row is skipped and
    logged at debug level.
    """
    items: list[NewsItem] = []
    for row in rows:
        try:
            items.append(to_item(row))
        except _BAD_ROW:
            log.debug("provider_item_skipped", provider=provider)
    return items
