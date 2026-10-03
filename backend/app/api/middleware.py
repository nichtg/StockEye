"""Request context (id, access log, security headers, 500 safety net) and CSRF enforcement."""

import re
import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.api.errors import error_response, unhandled_response
from app.auth.csrf import CSRF_COOKIE, CSRF_HEADER, UNSAFE_METHODS, csrf_valid
from app.logging_setup import get_logger

log = get_logger("app.access")

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
REQUEST_ID_HEADER = "X-Request-ID"

type CallNext = Callable[[Request], Awaitable[Response]]


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _REQUEST_ID_RE.fullmatch(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception as exc:
            response = await unhandled_response(request, exc)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        log.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.url.path.startswith("/api/auth/"):
            response.headers["Cache-Control"] = "no-store"
        structlog.contextvars.clear_contextvars()
        return response


class CsrfMiddleware(BaseHTTPMiddleware):
    """Double-submit CSRF check for every unsafe /api request.

    Middleware rather than a router dependency so that routers added later (stocks, ...) are
    protected by default: forgetting to attach a dependency cannot open a hole.
    """

    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        if request.method in UNSAFE_METHODS and request.url.path.startswith("/api"):
            cookie = request.cookies.get(CSRF_COOKIE)
            if not csrf_valid(cookie, request.headers.get(CSRF_HEADER)):
                return error_response(request, 403, "csrf_failed", "Missing or invalid CSRF token.")
        return await call_next(request)
