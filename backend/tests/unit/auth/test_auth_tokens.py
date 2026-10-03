from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import SecretStr

from app.auth.tokens import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_refresh_token,
    new_refresh_token,
)
from app.config import Settings

SECRET = "unit-test-secret-0123456789-0123456789"


@pytest.fixture
def cfg() -> Settings:
    return Settings(jwt_secret=SecretStr(SECRET), access_token_ttl_minutes=15)


def test_access_token_roundtrip_returns_subject(cfg: Settings) -> None:
    token = create_access_token("abc123", cfg)

    assert decode_access_token(token, cfg) == "abc123"


def test_access_token_expired_is_rejected(cfg: Settings) -> None:
    token = create_access_token("abc123", cfg, now=datetime.now(UTC) - timedelta(minutes=16))

    with pytest.raises(TokenError):
        decode_access_token(token, cfg)


def test_access_token_just_inside_ttl_is_accepted(cfg: Settings) -> None:
    token = create_access_token("abc123", cfg, now=datetime.now(UTC) - timedelta(minutes=14))

    assert decode_access_token(token, cfg) == "abc123"


def test_access_token_tampered_payload_is_rejected(cfg: Settings) -> None:
    head, payload, sig = create_access_token("abc123", cfg).split(".")
    flipped = payload[:-2] + ("AA" if payload[-2:] != "AA" else "BB")

    with pytest.raises(TokenError):
        decode_access_token(f"{head}.{flipped}.{sig}", cfg)


def test_access_token_signed_with_other_secret_is_rejected(cfg: Settings) -> None:
    other = Settings(jwt_secret=SecretStr("a-different-secret-0123456789-0123456789"))

    with pytest.raises(TokenError):
        decode_access_token(create_access_token("abc123", other), cfg)


def test_access_token_wrong_typ_is_rejected(cfg: Settings) -> None:
    now = datetime.now(UTC)
    claims = {"sub": "abc123", "iat": now, "exp": now + timedelta(minutes=5), "typ": "refresh"}
    token = jwt.encode(claims, SECRET, algorithm="HS256")

    with pytest.raises(TokenError):
        decode_access_token(token, cfg)


def test_access_token_missing_claims_is_rejected(cfg: Settings) -> None:
    token = jwt.encode({"sub": "abc123"}, SECRET, algorithm="HS256")

    with pytest.raises(TokenError):
        decode_access_token(token, cfg)


def test_access_token_alg_none_is_rejected(cfg: Settings) -> None:
    now = datetime.now(UTC)
    claims = {"sub": "x", "iat": now, "exp": now + timedelta(minutes=5), "typ": "access"}
    token = jwt.encode(claims, "", algorithm="none")

    with pytest.raises(TokenError):
        decode_access_token(token, cfg)


def test_refresh_token_is_unique_and_stored_as_sha256_hex() -> None:
    a, b = new_refresh_token(), new_refresh_token()

    assert a != b
    assert len(hash_refresh_token(a)) == 64
    assert hash_refresh_token(a) != a
    assert hash_refresh_token(a) == hash_refresh_token(a)
