from __future__ import annotations

from funnelhub.api.messenger import render_join_page
from funnelhub.config import Settings


def test_join_page_renders_vk_deep_link_without_oauth_authorization() -> None:
    response = render_join_page(
        Settings(
            VK_GROUP_SCREEN_NAME="aisu_test_vk",
            VK_GROUP_ID=123,
            VK_CALLBACK_SECRET="callback-secret",
            VK_OAUTH_CLIENT_ID="client-id",
            VK_OAUTH_CLIENT_SECRET="client-secret",
            VK_OAUTH_STATE_SECRET="state-secret",
        ),
        "token-123",
    )
    html = response.body.decode()

    assert 'href="http://localhost:8000/join/token-123/vk"' in html
    assert "id.vk.ru/authorize" not in html


def test_join_page_uses_simple_messenger_button_copy() -> None:
    response = render_join_page(
        Settings(
            TELEGRAM_BOT_USERNAME="aisu_test_bot",
            VK_GROUP_SCREEN_NAME="aisu_test_vk",
        ),
        "token-123",
    )
    html = response.body.decode()

    assert 'href="https://t.me/aisu_test_bot?start=token-123"' in html
    assert 'href="http://localhost:8000/join/token-123/vk"' in html
    assert "Открыть Telegram" in html
    assert "Открыть VK" in html
    assert "персон" not in html.lower()
    assert "ссылк" not in html.lower()
