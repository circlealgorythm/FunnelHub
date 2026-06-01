from funnelhub.vk_bot import (
    extract_token_from_payload,
    extract_token_from_text,
    extract_vk_message,
    extract_vk_start_token,
    extract_vk_user_id,
    is_stop_command,
    normalize_token,
)


def test_extract_vk_message_supports_callback_shape() -> None:
    event = {"object": {"message": {"from_id": 123, "text": "hello"}}}

    assert extract_vk_message(event) == {"from_id": 123, "text": "hello"}


def test_extract_vk_user_id() -> None:
    assert extract_vk_user_id({"from_id": 123}) == "123"
    assert extract_vk_user_id({"user_id": 456}) == "456"


def test_extract_vk_start_token_from_ref_payload_and_text() -> None:
    assert extract_vk_start_token({"ref": " token-ref "}) == "token-ref"
    assert extract_vk_start_token({"payload": '{"token":"token-payload"}'}) == "token-payload"
    assert extract_vk_start_token({"text": "/start token-text"}) == "token-text"


def test_extract_token_from_payload() -> None:
    assert extract_token_from_payload({"bot_link_token": "abc"}) == "abc"
    assert extract_token_from_payload('{"ref":"abc"}') == "abc"
    assert extract_token_from_payload("abc") == "abc"


def test_extract_token_from_text() -> None:
    assert extract_token_from_text("/start abc") == "abc"
    assert extract_token_from_text("начать abc") == "abc"
    assert extract_token_from_text("hello abc") is None


def test_normalize_token() -> None:
    assert normalize_token(" abc ") == "abc"
    assert normalize_token("") is None
    assert normalize_token(None) is None


def test_is_stop_command() -> None:
    assert is_stop_command("/stop") is True
    assert is_stop_command("стоп") is True
    assert is_stop_command("hello") is False
