from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from funnelhub.config import get_settings
from funnelhub.main import app
from funnelhub.services.auth import SESSION_COOKIE_NAME, hash_password, verify_password


def test_password_hash_verification() -> None:
    password_hash = hash_password("secret", salt=b"1234567890123456")

    assert verify_password("secret", password_hash) is True
    assert verify_password("wrong", password_hash) is False


async def test_login_me_and_logout(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    configure_auth(monkeypatch)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client:
            login_response = await client.post(
                "/api/auth/login",
                json={"username": "aisu", "password": "secret"},
            )
            me_response = await client.get("/api/auth/me")
            logout_response = await client.post("/api/auth/logout")
            logged_out_response = await client.get("/api/auth/me")
    finally:
        get_settings.cache_clear()

    assert login_response.status_code == 200
    assert login_response.json() == {
        "authenticated": True,
        "username": "aisu",
        "configured": True,
    }
    assert SESSION_COOKIE_NAME in login_response.cookies
    assert me_response.status_code == 200
    assert me_response.json()["username"] == "aisu"
    assert logout_response.status_code == 200
    assert logged_out_response.status_code == 401


async def test_login_rejects_invalid_password(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    configure_auth(monkeypatch)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client:
            response = await client.post(
                "/api/auth/login",
                json={"username": "aisu", "password": "wrong"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 401
    assert SESSION_COOKIE_NAME not in response.cookies


async def test_login_returns_503_when_not_configured(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("INBOX_ADMIN_USERNAME", "")
    monkeypatch.setenv("INBOX_ADMIN_PASSWORD_HASH", "")
    monkeypatch.setenv("INBOX_SESSION_SECRET", "")
    get_settings.cache_clear()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client:
            response = await client.post(
                "/api/auth/login",
                json={"username": "aisu", "password": "secret"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 503


async def test_inbox_api_requires_auth(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    configure_auth(monkeypatch)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client:
            response = await client.get("/api/inbox/conversations")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 401


def configure_auth(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("INBOX_ADMIN_USERNAME", "aisu")
    monkeypatch.setenv(
        "INBOX_ADMIN_PASSWORD_HASH",
        hash_password("secret", salt=b"1234567890123456"),
    )
    monkeypatch.setenv("INBOX_SESSION_SECRET", "test-session-secret")
    get_settings.cache_clear()
