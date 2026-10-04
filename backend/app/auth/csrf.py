"""Double-submit CSRF: unsafe requests must echo the ``se_csrf`` cookie in ``X-CSRF-Token``."""

import secrets

CSRF_COOKIE = "se_csrf"
CSRF_HEADER = "X-CSRF-Token"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_valid(cookie: str | None, header: str | None) -> bool:
    if not cookie or not header:
        return False
    return secrets.compare_digest(cookie.encode(), header.encode())
