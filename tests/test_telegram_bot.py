from aiogram.types import User

from funnelhub.db.models import MessengerIdentity
from funnelhub.telegram_bot import (
    build_raw_profile,
    build_status_text,
    build_stop_text,
    normalize_start_token,
)


def test_normalize_start_token() -> None:
    assert normalize_start_token(" abc ") == "abc"
    assert normalize_start_token("") is None
    assert normalize_start_token(None) is None


def test_build_raw_profile() -> None:
    user = User(
        id=123,
        is_bot=False,
        first_name="Test",
        last_name="User",
        username="test_user",
        language_code="ru",
        is_premium=True,
    )

    assert build_raw_profile(user) == {
        "id": 123,
        "is_bot": False,
        "first_name": "Test",
        "last_name": "User",
        "username": "test_user",
        "language_code": "ru",
        "is_premium": True,
    }


def test_build_status_text() -> None:
    assert (
        build_status_text(None)
        == "Telegram пока не привязан. Нажмите кнопку Telegram на странице после заявки."
    )

    subscribed_identity = MessengerIdentity(
        channel="telegram",
        external_user_id="123",
        is_subscribed=True,
        raw_profile={},
    )
    assert build_status_text(subscribed_identity) == "Telegram привязан. Подписка активна."

    unsubscribed_identity = MessengerIdentity(
        channel="telegram",
        external_user_id="123",
        is_subscribed=False,
        raw_profile={},
    )
    assert (
        build_status_text(unsubscribed_identity)
        == "Telegram привязан, но подписка остановлена. "
        "Нажмите кнопку Telegram на странице после заявки, чтобы включить снова."
    )


def test_build_stop_text() -> None:
    assert build_stop_text(True) == "Подписка в Telegram остановлена."
    assert build_stop_text(False) == "Telegram пока не привязан. Отписка не требуется."
