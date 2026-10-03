"""Yahoo Finance market data via yfinance (synchronous, so every call runs in a worker thread).

yfinance objects are untyped, so values cross the vendor boundary as ``Any`` and are validated
straight away into the normalized models.
"""

import asyncio
import math
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd
import yfinance as yf
from curl_cffi.requests.exceptions import RequestException as CurlRequestException
from requests.exceptions import RequestException
from yfinance.exceptions import YFRateLimitError, YFTickerMissingError

from app.logging_setup import get_logger
from app.providers.errors import (
    ProviderDataError,
    ProviderError,
    RateLimitedError,
    SymbolNotFoundError,
    TransientProviderError,
)
from app.providers.models import (
    Bar,
    CorporateEvent,
    Exchange,
    Interval,
    Quote,
    SymbolMatch,
)

log = get_logger(__name__)

_US_EXCHANGES = frozenset({"NMS", "NYQ", "NGM", "NCM", "ASE", "PCX", "BTS", "NYS", "NAS", "NGS"})
_SGX_EXCHANGES = frozenset({"SES"})
_ALLOWED_TYPES = frozenset({"EQUITY", "ETF"})
_MAX_SEARCH_RESULTS = 8
_EARNINGS_LIMIT = 40  # about ten years of quarters


def _exchange_of(code: object) -> Exchange | None:
    if code in _US_EXCHANGES:
        return "US"
    if code in _SGX_EXCHANGES:
        return "SGX"
    return None


def _is_nan(value: object) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


class YahooMarketData:
    name = "yahoo"

    async def _run[T](self, func: Callable[[], T], symbol: str = "") -> T:
        """Run blocking yfinance code in a thread, mapping its failures to our taxonomy."""
        try:
            return await asyncio.to_thread(func)
        except ProviderError:
            raise
        except YFRateLimitError as exc:
            raise RateLimitedError(self.name) from exc
        except YFTickerMissingError as exc:
            raise SymbolNotFoundError(self.name, f"unknown symbol {symbol}") from exc
        except (RequestException, CurlRequestException, TimeoutError, ConnectionError) as exc:
            raise TransientProviderError(
                self.name, f"network error ({type(exc).__name__})"
            ) from exc
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            raise ProviderDataError(
                self.name, f"unexpected payload ({type(exc).__name__})"
            ) from exc

    async def search(self, query: str) -> list[SymbolMatch]:
        raw = await self._run(lambda: list(yf.Search(query, max_results=10, news_count=0).quotes))
        matches: list[SymbolMatch] = []
        for item in raw:
            exchange = _exchange_of(item.get("exchange"))
            symbol = item.get("symbol")
            name = item.get("longname") or item.get("shortname")
            if (
                exchange is None
                or not symbol
                or not name
                or item.get("quoteType") not in _ALLOWED_TYPES
            ):
                continue
            matches.append(SymbolMatch(symbol=symbol, name=name, exchange=exchange))
            if len(matches) == _MAX_SEARCH_RESULTS:
                break
        return matches

    async def quote(self, symbol: str) -> Quote:
        def work() -> Quote:
            ticker = yf.Ticker(symbol)
            try:
                info = ticker.fast_info
                price = info.last_price
                previous = info.previous_close
            except KeyError as exc:  # no exchange metadata at all: Yahoo does not know it
                raise SymbolNotFoundError(self.name, f"unknown symbol {symbol}") from exc
            if _is_nan(price) or _is_nan(previous):
                raise SymbolNotFoundError(self.name, f"no quote for {symbol}")
            exchange = _exchange_of(info.exchange)
            if exchange is None:
                raise ProviderDataError(self.name, f"unsupported exchange {info.exchange!r}")
            try:
                name = ticker.info.get("longName") or ticker.info.get("shortName") or symbol
            except Exception:
                name = symbol
            return Quote(
                symbol=symbol,
                name=name,
                exchange=exchange,
                currency=info.currency,
                price=float(price),
                previous_close=float(previous),
                as_of=datetime.now(UTC),
            )

        return await self._run(work, symbol)

    async def bars(
        self, symbol: str, interval: Interval, start: datetime, end: datetime
    ) -> list[Bar]:
        def work() -> list[Bar]:
            frame = yf.Ticker(symbol).history(
                start=start, end=end, interval=interval, auto_adjust=True, actions=False
            )
            return _frame_to_bars(frame, interval)

        return await self._run(work, symbol)

    async def events(self, symbol: str, start: datetime, end: datetime) -> list[CorporateEvent]:
        first, last = start.date(), end.date()

        def core() -> list[CorporateEvent]:
            ticker = yf.Ticker(symbol)
            currency = ticker.fast_info.currency or ""
            out: list[CorporateEvent] = []
            for ts, amount in ticker.get_dividends().items():
                day = _as_date(ts)
                if first <= day <= last:
                    out.append(
                        CorporateEvent(
                            kind="dividend",
                            date=day,
                            label=f"Dividend {float(amount):g} {currency}".strip(),
                            value=float(amount),
                        )
                    )
            for ts, ratio in ticker.get_splits().items():
                day = _as_date(ts)
                if first <= day <= last and float(ratio) > 0:
                    out.append(
                        CorporateEvent(
                            kind="split",
                            date=day,
                            label=f"Split {_ratio_label(float(ratio))}",
                            value=float(ratio),
                        )
                    )
            return out

        def earnings() -> list[CorporateEvent]:
            frame = yf.Ticker(symbol).get_earnings_dates(limit=_EARNINGS_LIMIT)
            out: list[CorporateEvent] = []
            if frame is None:
                return out
            for ts, row in frame.iterrows():
                day = _as_date(ts)
                if not first <= day <= last:
                    continue
                actual, estimate = row.get("Reported EPS"), row.get("EPS Estimate")
                label = "Earnings"
                if not _is_nan(actual) and not _is_nan(estimate):
                    label = f"Earnings: EPS {float(actual):g} vs est {float(estimate):g}"
                elif not _is_nan(actual):
                    label = f"Earnings: EPS {float(actual):g}"
                out.append(
                    CorporateEvent(
                        kind="earnings",
                        date=day,
                        label=label,
                        value=None if _is_nan(actual) else float(actual),
                    )
                )
            return out

        async def optional_earnings() -> list[CorporateEvent]:
            try:
                return await self._run(earnings, symbol)
            except ProviderError as exc:
                # Partial success: dividends and splits are still worth returning.
                log.warning(
                    "provider_partial_result", provider=self.name, part="earnings", error=str(exc)
                )
                return []

        actions, reported = await asyncio.gather(self._run(core, symbol), optional_earnings())
        return sorted([*actions, *reported], key=lambda e: (e.date, e.kind))


def _as_date(ts: Any) -> date:
    """Calendar date of a vendor timestamp in its own (exchange-local) timezone."""
    return date(ts.year, ts.month, ts.day)


def _ratio_label(ratio: float) -> str:
    if ratio >= 1:
        return f"{ratio:g}:1"
    return f"1:{1 / ratio:g}"  # reverse split, e.g. 0.1 -> 1:10


def _frame_to_bars(frame: Any, interval: Interval) -> list[Bar]:
    if frame is None or frame.empty:
        return []
    frame = frame.dropna(subset=["Open", "High", "Low", "Close"])
    bars: list[Bar] = []
    for ts, row in frame.iterrows():
        if interval == "1d":
            stamp = datetime(ts.year, ts.month, ts.day, tzinfo=UTC)
        else:
            moment = pd.Timestamp(ts)
            moment = (
                moment.tz_localize("UTC") if moment.tzinfo is None else moment.tz_convert("UTC")
            )
            stamp = moment.to_pydatetime()
        volume = row.get("Volume")
        bars.append(
            Bar(
                ts=stamp,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=0.0 if _is_nan(volume) else float(volume),
            )
        )
    return bars
