from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient, Response

from funnelhub.config import Settings
from funnelhub.main import create_app
from funnelhub.services.funnel_runner import (
    is_permanent_delivery_error,
    pause_funnel_state_after_permanent_delivery_error,
)
from funnelhub.services.vk_messaging import (
    HttpVkMessageClient,
    VkApiError,
    VkPermissionRevokedError,
    VkTokenInvalidError,
)


def test_cors_allowed_origins_parsing() -> None:
    settings = Settings(CORS_ALLOWED_ORIGINS="https://aisukam.ru, https://app.aisukam.ru")
    assert settings.cors_allowed_origins == ["https://aisukam.ru", "https://app.aisukam.ru"]

    settings_json = Settings(CORS_ALLOWED_ORIGINS='["https://aisukam.ru", "https://api.aisukam.ru"]')
    assert settings_json.cors_allowed_origins == ["https://aisukam.ru", "https://api.aisukam.ru"]

    settings_empty = Settings(CORS_ALLOWED_ORIGINS="")
    assert settings_empty.cors_allowed_origins == []


@pytest.mark.asyncio
async def test_cors_middleware_allows_trusted_origin_and_blocks_untrusted(monkeypatch) -> None:
    from funnelhub.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://trusted-site.com,https://app.trusted-site.com")
    try:
        app = create_app()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Разрешенный Origin
            allowed_res = await client.options(
                "/health",
                headers={
                    "Origin": "https://trusted-site.com",
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert allowed_res.headers.get("access-control-allow-origin") == "https://trusted-site.com"
            assert allowed_res.headers.get("access-control-allow-credentials") == "true"

            # Неразрешенный Origin (злоумышленник)
            blocked_res = await client.options(
                "/health",
                headers={
                    "Origin": "https://evil-attacker.com",
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert "access-control-allow-origin" not in blocked_res.headers
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_vk_client_classifies_errors_accurately() -> None:
    client = HttpVkMessageClient(access_token="fake_token", api_version="5.199")

    # Код 901: без разрешения
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Response(
            200,
            json={
                "error": {
                    "error_code": 901,
                    "error_msg": "Can't send messages for users without permission",
                }
            },
            request=mock_post,
        )
        with pytest.raises(VkPermissionRevokedError) as exc_info:
            await client.send_message(peer_id="123", message="hi")
        assert exc_info.value.error_code == 901

    # Код 902: настройки приватности
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Response(
            200,
            json={
                "error": {
                    "error_code": 902,
                    "error_msg": "Can't send messages to this user due to their privacy settings",
                }
            },
            request=mock_post,
        )
        with pytest.raises(VkPermissionRevokedError) as exc_info:
            await client.send_message(peer_id="123", message="hi")
        assert exc_info.value.error_code == 902

    # Код 18: пользователь удален/заблокирован
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Response(
            200,
            json={"error": {"error_code": 18, "error_msg": "User was deleted or banned"}},
            request=mock_post,
        )
        with pytest.raises(VkPermissionRevokedError):
            await client.send_message(peer_id="123", message="hi")

    # Код 5: токен группы недействителен / отозван
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Response(
            200,
            json={
                "error": {
                    "error_code": 5,
                    "error_msg": "User authorization failed: access_token has expired",
                }
            },
            request=mock_post,
        )
        with pytest.raises(VkTokenInvalidError) as exc_info:
            await client.send_message(peer_id="123", message="hi")
        assert exc_info.value.error_code == 5

    # Общая ошибка API
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Response(
            200,
            json={
                "error": {
                    "error_code": 100,
                    "error_msg": "One of the parameters specified was missing or invalid",
                }
            },
            request=mock_post,
        )
        with pytest.raises(VkApiError):
            await client.send_message(peer_id="123", message="hi")


def test_permanent_delivery_error_recognition() -> None:
    perm_err = VkPermissionRevokedError(
        "Can't send messages to this user due to their privacy settings", error_code=902
    )
    assert is_permanent_delivery_error(perm_err) is True

    token_err = VkTokenInvalidError("User authorization failed: invalid session", error_code=5)
    assert is_permanent_delivery_error(token_err) is True


@pytest.mark.asyncio
async def test_pause_funnel_state_fail_closed_logic() -> None:
    class MockState:
        def __init__(self) -> None:
            self.id = uuid.uuid4()
            self.lead_id = uuid.uuid4()
            self.status = "active"
            self.paused_at = None
            self.next_run_at = datetime.now(UTC)
            self.metadata_ = {}

    class MockSession:
        def __init__(self, state: MockState) -> None:
            self._state = state

        async def get(self, model, ident):  # type: ignore[no-untyped-def]
            return self._state

        async def scalar(self, statement):  # type: ignore[no-untyped-def]
            return None

        async def flush(self) -> None:
            pass

    # 1. При ошибке отзыва прав VK
    state1 = MockState()
    session1 = MockSession(state1)
    err1 = VkPermissionRevokedError(
        "Can't send messages to this user due to their privacy settings", error_code=902
    )
    res1 = await pause_funnel_state_after_permanent_delivery_error(
        session=session1,  # type: ignore[arg-type]
        state_id=state1.id,
        error=err1,
        now=datetime.now(UTC),
    )
    assert res1 is True
    assert state1.status == "paused"
    assert state1.next_run_at is None
    assert state1.metadata_["paused_reason"] == "permanent_delivery_error"

    # 2. При ошибке недействительного токена сообщества VK
    state2 = MockState()
    session2 = MockSession(state2)
    err2 = VkTokenInvalidError("User authorization failed: access_token has expired", error_code=5)
    res2 = await pause_funnel_state_after_permanent_delivery_error(
        session=session2,  # type: ignore[arg-type]
        state_id=state2.id,
        error=err2,
        now=datetime.now(UTC),
    )
    assert res2 is True
    assert state2.status == "paused"
    assert state2.next_run_at is None
    assert state2.metadata_["paused_reason"] == "vk_token_invalid"
