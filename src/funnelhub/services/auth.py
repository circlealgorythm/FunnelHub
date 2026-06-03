from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Cookie, Depends, HTTPException, status

from funnelhub.config import Settings, get_settings

SESSION_COOKIE_NAME = "funnelhub_admin_session"
PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 390_000


@dataclass(frozen=True)
class AuthenticatedAdmin:
    username: str


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    if not password:
        raise ValueError("Password is required.")

    password_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        password_salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return "$".join(
        [
            PASSWORD_HASH_ALGORITHM,
            str(PASSWORD_HASH_ITERATIONS),
            encode_base64url(password_salt),
            encode_base64url(digest),
        ]
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, expected_raw = password_hash.split("$", maxsplit=3)
        if algorithm != PASSWORD_HASH_ALGORITHM:
            return False
        iterations = int(iterations_raw)
        salt = decode_base64url(salt_raw)
        expected = decode_base64url(expected_raw)
    except (ValueError, TypeError):
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return secrets.compare_digest(actual, expected)


def authenticate_admin(settings: Settings, username: str, password: str) -> bool:
    if not is_auth_configured(settings):
        return False

    configured_username = settings.inbox_admin_username or ""
    configured_hash = settings.inbox_admin_password_hash or ""
    username_matches = secrets.compare_digest(username.strip(), configured_username)
    password_matches = verify_password(password, configured_hash)
    return username_matches and password_matches


def create_session_cookie(settings: Settings, username: str, now: int | None = None) -> str:
    secret = get_session_secret(settings)
    issued_at = int(now if now is not None else time.time())
    expires_at = issued_at + settings.inbox_session_ttl_seconds
    payload = {
        "username": username,
        "iat": issued_at,
        "exp": expires_at,
    }
    encoded_payload = encode_base64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = sign_value(secret, encoded_payload)
    return f"{encoded_payload}.{signature}"


def verify_session_cookie(
    settings: Settings,
    cookie_value: str | None,
) -> AuthenticatedAdmin | None:
    if not is_auth_configured(settings) or not cookie_value:
        return None

    secret = get_session_secret(settings)
    try:
        encoded_payload, signature = cookie_value.split(".", maxsplit=1)
    except ValueError:
        return None

    expected_signature = sign_value(secret, encoded_payload)
    if not secrets.compare_digest(signature, expected_signature):
        return None

    try:
        payload = json.loads(decode_base64url(encoded_payload))
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None
    username = payload.get("username")
    expires_at = payload.get("exp")
    if not isinstance(username, str) or not isinstance(expires_at, int | float):
        return None
    if expires_at < time.time():
        return None
    if not secrets.compare_digest(username, settings.inbox_admin_username or ""):
        return None

    return AuthenticatedAdmin(username=username)


def is_auth_configured(settings: Settings) -> bool:
    return bool(
        settings.inbox_admin_username
        and settings.inbox_admin_password_hash
        and settings.inbox_session_secret
    )


def get_session_secret(settings: Settings) -> bytes:
    secret = settings.inbox_session_secret
    if not secret:
        raise ValueError("INBOX_SESSION_SECRET is not configured.")
    return secret.encode("utf-8")


def should_use_secure_cookie(settings: Settings) -> bool:
    return settings.public_base_url.startswith("https://")


async def require_admin_session(
    settings: Annotated[Settings, Depends(get_settings)],
    session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> AuthenticatedAdmin:
    admin = verify_session_cookie(settings, session_cookie)
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return admin


def sign_value(secret: bytes, value: str) -> str:
    return hmac.new(secret, value.encode("utf-8"), hashlib.sha256).hexdigest()


def encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def decode_base64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def safe_auth_status(settings: Settings) -> dict[str, Any]:
    return {
        "configured": is_auth_configured(settings),
        "session_ttl_seconds": settings.inbox_session_ttl_seconds,
    }
