"""One error envelope for every failure: {"error": {code, message, request_id, details}}."""

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException

from app.logging_setup import get_logger
from app.services.errors import AppError

__all__ = ["AppError", "error_response", "install_error_handlers", "unhandled_response"]

log = get_logger(__name__)

_CODES = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
}


def request_id_of(request: Request) -> str:
    return str(getattr(request.state, "request_id", ""))


def error_response(
    request: Request,
    status: int,
    code: str,
    message: str,
    *,
    details: list[dict[str, Any]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id_of(request),
            "details": details,
        }
    }
    return JSONResponse(body, status_code=status, headers=headers)


async def _http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HTTPException)  # noqa: S101 - narrows the handler's declared type
    code = _CODES.get(exc.status_code, "http_error")
    message = exc.detail if isinstance(exc.detail, str) else code.replace("_", " ")
    return error_response(request, exc.status_code, code, message, headers=exc.headers)


async def _app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)  # noqa: S101
    return error_response(request, exc.status, exc.code, exc.message, details=exc.details)


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    details = []
    for err in exc.errors():
        message = str(err["msg"]).removeprefix("Value error, ")
        details.append({"field": ".".join(str(p) for p in err["loc"][1:]), "message": message})
    first = details[0]["message"] if details else "Invalid request."
    return error_response(
        request, 422, "validation_error", first, details=jsonable_encoder(details)
    )


async def _rate_limited(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RateLimitExceeded)  # noqa: S101
    return error_response(
        request, 429, "rate_limited", "Too many requests. Please slow down and try again shortly."
    )


async def unhandled_response(request: Request, exc: Exception) -> JSONResponse:
    """500 envelope. The traceback goes to the log only; the client gets a generic message."""
    log.error("unhandled_exception", path=request.url.path, exc_info=exc)
    return error_response(request, 500, "internal_error", "Something went wrong on our side.")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, _http_exception)
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(RateLimitExceeded, _rate_limited)
    app.add_exception_handler(Exception, unhandled_response)
