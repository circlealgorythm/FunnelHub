from __future__ import annotations

import json

import pytest

from funnelhub.config import Settings
from funnelhub.services.vk_oauth import (
    base64url_decode,
    base64url_encode,
    build_code_challenge,
    build_vk_oauth_join_url,
    build_vk_oauth_redirect_uri,
    build_vk_oauth_state,
    extract_vk_user_id,
    is_vk_oauth_configured,
    parse_vk_oauth_state,
)


def build_settings() -> Settings:
    return Settings(
        PUBLIC_BASE_URL="https://bot.example.test",
        VK_CALLBACK_SECRET="callback-secret",
        VK_GROUP_ID=123,
        VK_OAUTH_CLIENT_ID="client-id",
        VK_OAUTH_CLIENT_SECRET="client-secret",
        VK_OAUTH_STATE_SECRET="state-secret",
    )


def test_vk_oauth_configured_requires_client_group_and_state_secret() -> None:
    assert is_vk_oauth_configured(build_settings()) is True
    assert is_vk_oauth_configured(Settings()) is False


def test_vk_oauth_state_round_trip_and_rejects_tampering() -> None:
    settings = build_settings()
    state = build_vk_oauth_state(
        settings,
        "token-123",
        issued_at=1_000,
        code_verifier="verifier-123",
    )

    parsed = parse_vk_oauth_state(settings, state, now=1_100)
    assert parsed.token == "token-123"
    assert parsed.code_verifier == "verifier-123"

    state_payload = json.loads(base64url_decode(state).decode())
    state_payload["p"] = f"{state_payload['p'][:-1]}A"
    tampered_state = base64url_encode(json.dumps(state_payload).encode())
    with pytest.raises(ValueError, match="signature"):
        parse_vk_oauth_state(settings, tampered_state, now=1_100)


def test_vk_oauth_state_expires() -> None:
    settings = build_settings()
    state = build_vk_oauth_state(
        settings,
        "token-123",
        issued_at=1_000,
        code_verifier="verifier-123",
    )

    with pytest.raises(ValueError, match="expired"):
        parse_vk_oauth_state(settings, state, now=2_000)


def test_build_vk_oauth_join_url() -> None:
    settings = build_settings()
    url = build_vk_oauth_join_url(settings, "token-123")

    assert url is not None
    assert url.startswith("https://id.vk.ru/authorize?")
    assert "client_id=client-id" in url
    assert "response_type=code" in url
    assert "state=" in url
    assert "code_challenge=" in url
    assert "code_challenge_method=S256" in url
    assert build_vk_oauth_redirect_uri(settings) == "https://bot.example.test/oauth/vk/callback"


def test_build_code_challenge_uses_s256() -> None:
    assert build_code_challenge("verifier-123") == "Ds3NpaREu9I2EYq6l0l3ZkFyv_Gt5O4EpGD6cZlY0Kg"


def test_extract_vk_user_id_from_id_token() -> None:
    header = base64url_encode(json.dumps({"alg": "none"}).encode())
    payload = base64url_encode(json.dumps({"sub": 123456}).encode())
    token = f"{header}.{payload}.signature"

    assert extract_vk_user_id({"id_token": token}) == "123456"
