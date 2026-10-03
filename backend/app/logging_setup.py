"""Structured JSON logging via structlog. Lines carry ``request_id`` inside a request.

Credentials never reach a log line: vendor HTTP libraries are silenced below WARNING, and both
the stdlib root handlers and the structlog pipeline pass everything through ``redact_text``.
"""

import logging

import structlog
from structlog.types import EventDict, WrappedLogger

from app.redaction import redact_text

# Their INFO lines print the full request URL, which for some vendors contains the API key.
_NOISY_HTTP_LOGGERS = ("httpx", "httpcore")


class RedactingFilter(logging.Filter):
    """Redact the formatted message and traceback of every record that passes through."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage())
        record.args = None
        if record.exc_info and not record.exc_text:
            # Format here so the traceback (which may quote a URL) is scrubbed too.
            record.exc_text = redact_text(logging.Formatter().formatException(record.exc_info))
        elif record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        return True


def _redact_value(value: object) -> object:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_redact_value(v) for v in value]
    return value


def redact_event(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    """structlog processor: scrub every string in the event, however deeply nested."""
    return {key: _redact_value(value) for key, value in event_dict.items()}


def configure_logging(level: str) -> None:
    logging.basicConfig(format="%(message)s", level=level)
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, RedactingFilter) for f in handler.filters):
            handler.addFilter(RedactingFilter())
    for name in _NOISY_HTTP_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            redact_event,  # after format_exc_info so rendered tracebacks are scrubbed too
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
