"""Cookie helpers. All cookies are SameSite=Lax; Secure follows ``settings.cookie_secure``."""

from fastapi import Response

from app.auth.csrf import CSRF_COOKIE
from app.config import Settings

ACCESS_COOKIE = "se_access"
REFRESH_COOKIE = "se_refresh"
ACCESS_PATH = "/api"
REFRESH_PATH = "/api/auth"


def set_auth_cookies(response: Response, settings: Settings, access: str, refresh: str) -> None:
    # Refresh is scoped to /api/auth so it is never sent with ordinary API calls.
    response.set_cookie(
        ACCESS_COOKIE,
        access,
        max_age=settings.access_token_ttl_minutes * 60,
        path=ACCESS_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        max_age=settings.refresh_token_ttl_days * 86400,
        path=REFRESH_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


def set_csrf_cookie(response: Response, settings: Settings, token: str) -> None:
    # Readable by the SPA on purpose: it copies the value into the X-CSRF-Token header.
    response.set_cookie(
        CSRF_COOKIE,
        token,
        max_age=settings.refresh_token_ttl_days * 86400,
        path="/",
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    for name, path in ((ACCESS_COOKIE, ACCESS_PATH), (REFRESH_COOKIE, REFRESH_PATH)):
        response.delete_cookie(
            name, path=path, httponly=True, secure=settings.cookie_secure, samesite="lax"
        )
