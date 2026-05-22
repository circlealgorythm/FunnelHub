from aiogram.types import User

from funnelhub.telegram_bot import build_raw_profile, normalize_start_token


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
