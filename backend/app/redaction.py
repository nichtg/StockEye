"""Scrub API credentials out of free text before it reaches a log line.

Vendors that take their key as a query parameter (``?apikey=...``) put it in the URL, and
HTTP libraries love to log URLs. Every log path funnels through ``redact_text`` so a key can
never be written, whichever library produced the line.
"""

import re

REDACTED = "REDACTED"

# ``token=``, ``apikey=``, ``api_token=`` and ``api_key=`` up to the next delimiter. The lookbehind
# stops the shorter ``token`` matching inside longer names such as ``csrf_token``.
_SECRET_PARAM = re.compile(
    r"(?P<name>(?<![\w])(?:token|apikey|api_token|api_key))=(?P<value>[^&\s\"'<>]+)",
    re.IGNORECASE,
)


def redact_text(text: str) -> str:
    """Replace the value of every secret query parameter in ``text`` with ``REDACTED``."""
    return _SECRET_PARAM.sub(rf"\g<name>={REDACTED}", text)
