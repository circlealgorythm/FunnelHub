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


async def test_login_rate_limiting(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from funnelhub.services.ingestion_guard import auth_login_rate_limiter

    configure_auth(monkeypatch)
    monkeypatch.setenv("INBOX_LOGIN_RATE_LIMIT_PER_MINUTE", "3")
    get_settings.cache_clear()
    auth_login_rate_limiter.reset()

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client:
            for _ in range(3):
                res = await client.post(
                    "/api/auth/login",
                    json={"username": "aisu", "password": "wrong"},
                )
                assert res.status_code == 401

            blocked_res = await client.post(
                "/api/auth/login",
                json={"username": "aisu", "password": "wrong"},
            )
            assert blocked_res.status_code == 429
            assert "Too many login attempts" in blocked_res.json()["detail"]
    finally:
        auth_login_rate_limiter.reset()
        get_settings.cache_clear()

async def test_login_rate_limiting_ip_spoofing_prevention(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from funnelhub.services.ingestion_guard import auth_login_rate_limiter

    configure_auth(monkeypatch)
    monkeypatch.setenv("INBOX_LOGIN_RATE_LIMIT_PER_MINUTE", "2")
    get_settings.cache_clear()
    auth_login_rate_limiter.reset()

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client:
            headers_1 = {"x-forwarded-for": "1.1.1.1, 192.168.1.50"}
            headers_2 = {"x-forwarded-for": "2.2.2.2, 192.168.1.50"}
            headers_3 = {"x-forwarded-for": "3.3.3.3, 192.168.1.50"}

            payload = {"username": "aisu", "password": "wrong"}
            res1 = await client.post("/api/auth/login", json=payload, headers=headers_1)
            assert res1.status_code == 401

            res2 = await client.post("/api/auth/login", json=payload, headers=headers_2)
            assert res2.status_code == 401

            res3 = await client.post("/api/auth/login", json=payload, headers=headers_3)
            assert res3.status_code == 429
    finally:
        auth_login_rate_limiter.reset()
        get_settings.cache_clear()


def test_rate_limiter_memory_pruning() -> None:
    from funnelhub.services.ingestion_guard import InMemoryRateLimiter

    limiter = InMemoryRateLimiter()
    for i in range(550):
        limiter.check(f"ip_{i}", limit=10, window_seconds=60, now=100.0)

    assert len(limiter.buckets) == 550

    limiter.check("ip_fresh", limit=10, window_seconds=60, now=200.0)
    assert len(limiter.buckets) == 1
    assert "ip_fresh" in limiter.buckets

async def test_logout_revokes_session_cookie(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    configure_auth(monkeypatch)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client:
            login_res = await client.post(
                "/api/auth/login",
                json={"username": "aisu", "password": "secret"},
            )
            assert login_res.status_code == 200
            cookie_val = login_res.cookies.get(SESSION_COOKIE_NAME)
            assert cookie_val is not None

            # Authenticated check
            me_res = await client.get("/api/auth/me")
            assert me_res.status_code == 200

            # Logout
            logout_res = await client.post("/api/auth/logout")
            assert logout_res.status_code == 200

            # Attacker attempts replay of the previous session cookie
            replay_client = AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://127.0.0.1:8000",
                cookies={SESSION_COOKIE_NAME: cookie_val},
            )
            async with replay_client:
                replay_res = await replay_client.get("/api/auth/me")
                assert replay_res.status_code == 401
    finally:
        get_settings.cache_clear()


def test_sanitize_spreadsheet_cell_formula_injection() -> None:
    from funnelhub.services.inbox_database import sanitize_spreadsheet_cell

    # Dangerous formulas must be escaped with prepended single quote
    assert sanitize_spreadsheet_cell("=cmd|'/C calc'!A0") == "'=cmd|'/C calc'!A0"
    assert sanitize_spreadsheet_cell("  =1+1") == "'  =1+1"
    assert sanitize_spreadsheet_cell("@SUM(A1:A10)") == "'@SUM(A1:A10)"
    assert sanitize_spreadsheet_cell("+cmd|...") == "'+cmd|..."
    assert sanitize_spreadsheet_cell("-2+3*cmd|...") == "'-2+3*cmd|..."
    assert sanitize_spreadsheet_cell("\t=test") == "'\t=test"
    assert sanitize_spreadsheet_cell("\r=test") == "'\r=test"

    # Normal values must remain untouched
    assert sanitize_spreadsheet_cell("Иван Иванов") == "Иван Иванов"
    assert sanitize_spreadsheet_cell("test@example.com") == "test@example.com"
    assert sanitize_spreadsheet_cell("+79991234567") == "+79991234567"
    assert sanitize_spreadsheet_cell("+7 999 123-45-67") == "+7 999 123-45-67"
    assert sanitize_spreadsheet_cell("-500") == "-500"
    assert sanitize_spreadsheet_cell(12345) == 12345
    assert sanitize_spreadsheet_cell(None) is None
