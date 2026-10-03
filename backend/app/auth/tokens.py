"""Access JWTs and opaque refresh tokens."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt

from app.config import Settings

_ALGORITHM = "HS256"
_ACCESS_TYP = "access"


class TokenError(Exception):
    """The token is missing, malformed, expired, tampered with or of the wrong type."""


def create_access_token(user_id: str, settings: Settings, now: datetime | None = None) -> str:
    issued = now or datetime.now(UTC)
    claims = {
        "sub": user_id,
        "iat": issued,
        "exp": issued + timedelta(minutes=settings.access_token_ttl_minutes),
        "typ": _ACCESS_TYP,
    }
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm=_ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> str:
    """Return the user id (``sub``) of a valid access token, else raise ``TokenError``."""
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[_ALGORITHM],  # pinned: never trust the header's alg
            options={"require": ["sub", "iat", "exp", "typ"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError("invalid access token") from exc
    if claims["typ"] != _ACCESS_TYP or not isinstance(claims["sub"], str):
        raise TokenError("wrong token type")
    return claims["sub"]


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """sha256 hex digest; only this is stored, so a DB leak does not leak usable tokens."""
    return hashlib.sha256(token.encode()).hexdigest()
