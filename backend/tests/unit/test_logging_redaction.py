"""API keys must never reach a log line, whichever library or logger writes it."""

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest
import respx
import structlog

from app.logging_setup import configure_logging, redact_event
from app.providers.finnhub import FinnhubNews
from app.providers.models import NewsQuery
from app.redaction import redact_text

KEY = "sup3r-s3cret-key"


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    levels = {n: logging.getLogger(n).level for n in ("httpx", "httpcore")}
    yield
    for name, level in levels.items():
        logging.getLogger(name).setLevel(level)
    structlog.reset_defaults()


@pytest.mark.parametrize("param", ["token", "apikey", "api_token", "api_key", "TOKEN", "ApiKey"])
def test_redact_text_secret_param_value_is_replaced(param: str) -> None:
    text = f"GET https://vendor.example/v1/x?symbol=AAPL&{param}={KEY}&to=2026 HTTP/1.1"

    redacted = redact_text(text)

    assert KEY not in redacted
    assert f"{param}=REDACTED&to=2026" in redacted


def test_redact_text_unrelated_parameters_are_untouched() -> None:
    text = "https://x.example/?symbol=AAPL&csrf_token_hint=a&page=2"

    assert redact_text(text) == text


@respx.mock
async def test_finnhub_fetch_never_writes_the_key_to_logs(caplog: pytest.LogCaptureFixture) -> None:
    configure_logging("INFO")  # the app's own setup is what silences httpx's INFO URL lines
    route = respx.get("https://finnhub.io/api/v1/company-news").respond(200, json=[])
    query = NewsQuery(
        symbol="AAPL",
        exchange="US",
        company_name="Apple Inc.",
        start=datetime(2026, 9, 1, tzinfo=UTC),
        end=datetime(2026, 10, 1, tzinfo=UTC),
    )

    with caplog.at_level(logging.DEBUG):
        async with httpx.AsyncClient() as client:
            await FinnhubNews(client, KEY).fetch(query)

    request = route.calls.last.request
    assert request.headers["X-Finnhub-Token"] == KEY
    assert KEY not in str(request.url)
    assert KEY not in caplog.text


def test_configure_logging_silences_httpx_and_httpcore_below_warning() -> None:
    configure_logging("DEBUG")

    assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() == logging.WARNING


def test_stdlib_root_handlers_redact_secrets_in_any_logger(
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_logging("INFO")

    logging.getLogger("some.library").warning("GET %s", f"https://v.example/?apikey={KEY}")

    assert KEY not in caplog.text
    assert "apikey=REDACTED" in caplog.text


def test_stdlib_root_handlers_redact_secrets_in_tracebacks(
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_logging("INFO")

    try:
        raise RuntimeError(f"failed https://v.example/?token={KEY}")  # noqa: TRY301
    except RuntimeError:
        logging.getLogger("some.library").exception("boom")

    assert KEY not in caplog.text


def test_structlog_processor_redacts_nested_values() -> None:
    event = {"event": f"fetch ?apikey={KEY}", "extra": {"urls": [f"https://x/?token={KEY}"]}}

    cleaned = redact_event(None, "info", event)

    assert KEY not in json.dumps(cleaned)


def test_structlog_pipeline_redacts_event_output(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")

    structlog.get_logger("t").info("calling", url=f"https://v.example/?api_token={KEY}")

    assert KEY not in capsys.readouterr().out
