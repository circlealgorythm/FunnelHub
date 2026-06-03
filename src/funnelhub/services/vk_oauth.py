from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from funnelhub.config import Settings

VK_OAUTH_BASE_URL = "https://id.vk.ru/authorize"
VK_OAUTH_TOKEN_URL = "https://id.vk.ru/oauth2/auth"
VK_OAUTH_USER_INFO_URL = "https://id.vk.ru/oauth2/user_info"
VK_API_BASE_URL = "https://api.vk.com/method"
VK_OAUTH_STATE_TTL_SECONDS = 15 * 60
VK_OAUTH_SCOPE = "vkid.personal_info"


@dataclass(frozen=True)
class VkOAuthToken:
    access_token: str
    user_id: str
    raw_payload: dict[str, Any]


@dataclass(frozen=True)
class VkOAuthState:
    token: str
    code_verifier: str


def is_vk_oauth_configured(settings: Settings) -> bool:
    return bool(
        settings.vk_oauth_client_id
        and settings.vk_oauth_client_secret
        and settings.vk_group_id
        and vk_oauth_state_secret(settings)
    )


def build_vk_oauth_join_url(settings: Settings, token: str) -> str | None:
    if not is_vk_oauth_configured(settings):
        return None

    redirect_uri = build_vk_oauth_redirect_uri(settings)
    code_verifier = build_code_verifier()
    query = urlencode(
        {
            "client_id": settings.vk_oauth_client_id,
            "redirect_uri": redirect_uri,
            "display": "page",
            "scope": VK_OAUTH_SCOPE,
            "response_type": "code",
            "state": build_vk_oauth_state(settings, token, code_verifier=code_verifier),
            "code_challenge": build_code_challenge(code_verifier),
            "code_challenge_method": "S256",
        }
    )
    return f"{VK_OAUTH_BASE_URL}?{query}"


def build_vk_oauth_redirect_uri(settings: Settings) -> str:
    return f"{settings.public_base_url.rstrip('/')}/oauth/vk/callback"


def build_vk_oauth_state(
    settings: Settings,
    token: str,
    issued_at: int | None = None,
    code_verifier: str | None = None,
) -> str:
    payload = {
        "token": token,
        "iat": issued_at or int(time.time()),
        "code_verifier": code_verifier or build_code_verifier(),
    }
    encoded_payload = base64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = sign_state_payload(settings, encoded_payload)
    state_payload = {
        "p": encoded_payload,
        "s": signature,
    }
    return base64url_encode(json.dumps(state_payload, separators=(",", ":")).encode())


def parse_vk_oauth_state(settings: Settings, state: str, now: int | None = None) -> VkOAuthState:
    try:
        state_payload = json.loads(base64url_decode(state).decode())
        encoded_payload = state_payload["p"]
        signature = state_payload["s"]
    except (KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid VK OAuth state.") from exc
    if not isinstance(encoded_payload, str) or not isinstance(signature, str):
        raise ValueError("Invalid VK OAuth state.")

    expected_signature = sign_state_payload(settings, encoded_payload)
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("Invalid VK OAuth state signature.")

    try:
        payload = json.loads(base64url_decode(encoded_payload).decode())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid VK OAuth state payload.") from exc

    token = payload.get("token")
    issued_at = payload.get("iat")
    code_verifier = payload.get("code_verifier")
    if not isinstance(token, str) or not token:
        raise ValueError("Invalid VK OAuth state token.")
    if not isinstance(issued_at, int):
        raise ValueError("Invalid VK OAuth state timestamp.")
    if not isinstance(code_verifier, str) or not code_verifier:
        raise ValueError("Invalid VK OAuth state code verifier.")
    if (now or int(time.time())) - issued_at > VK_OAUTH_STATE_TTL_SECONDS:
        raise ValueError("VK OAuth state expired.")
    return VkOAuthState(token=token, code_verifier=code_verifier)


async def exchange_vk_oauth_code(
    settings: Settings,
    code: str,
    code_verifier: str,
    device_id: str | None = None,
    state: str | None = None,
) -> VkOAuthToken:
    if not settings.vk_oauth_client_id or not settings.vk_oauth_client_secret:
        raise ValueError("VK OAuth is not configured.")

    params = {
        "grant_type": "authorization_code",
        "client_id": settings.vk_oauth_client_id,
        "redirect_uri": build_vk_oauth_redirect_uri(settings),
        "code_verifier": code_verifier,
        "v": settings.vk_api_version,
    }
    if device_id:
        params["device_id"] = device_id
    if state:
        params["state"] = state

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(VK_OAUTH_TOKEN_URL, params=params, data={"code": code})
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, dict):
        raise ValueError("VK OAuth token response must be an object.")
    if "error" in payload:
        raise ValueError(
            "VK OAuth token exchange failed: "
            f"{payload.get('error_description') or payload['error']}; "
            f"response_keys={sorted(payload.keys())}"
        )

    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise ValueError("VK OAuth response has no access_token.")

    user_id = extract_vk_user_id(payload)
    if user_id is None:
        try:
            user_info = await fetch_vk_oauth_user_info(settings, access_token)
        except ValueError as exc:
            token_keys = sorted(payload.keys())
            has_id_token = "id_token" in payload
            raise ValueError(
                "VK OAuth user id not found; "
                f"token_response_keys={token_keys}; "
                f"has_id_token={has_id_token}; "
                f"user_info_error={exc}"
            ) from exc
        user_id = extract_vk_user_id(user_info)
        payload = {**payload, "user_info_keys": sorted(user_info.keys())}

    if user_id is None:
        raise ValueError("VK OAuth response has no user id.")

    return VkOAuthToken(
        access_token=access_token,
        user_id=str(user_id),
        raw_payload=payload,
    )


async def fetch_vk_oauth_user_info(
    settings: Settings,
    access_token: str,
) -> dict[str, Any]:
    if not settings.vk_oauth_client_id:
        raise ValueError("VK OAuth is not configured.")

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            VK_OAUTH_USER_INFO_URL,
            data={
                "access_token": access_token,
                "client_id": settings.vk_oauth_client_id,
            },
        )
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, dict):
        raise ValueError("VK OAuth user_info response must be an object.")
    if "error" in payload:
        raise ValueError(str(payload.get("error_description") or payload["error"]))
    return payload


def extract_vk_user_id(payload: dict[str, Any]) -> str | None:
    for key in ("user_id", "id", "sub"):
        value = payload.get(key)
        if isinstance(value, str | int) and str(value):
            return str(value)

    id_token = payload.get("id_token")
    if isinstance(id_token, str) and id_token:
        id_token_payload = decode_jwt_payload(id_token)
        if id_token_payload:
            return extract_vk_user_id(id_token_payload)

    user = payload.get("user")
    if isinstance(user, dict):
        for key in ("user_id", "id", "sub"):
            value = user.get(key)
            if isinstance(value, str | int) and str(value):
                return str(value)

    response = payload.get("response")
    if isinstance(response, dict):
        return extract_vk_user_id(response)

    return None


def decode_jwt_payload(token: str) -> dict[str, Any] | None:
    parts = token.split(".")
    if len(parts) < 2:
        return None
    try:
        payload = json.loads(base64url_decode(parts[1]).decode())
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


async def allow_vk_messages_from_group(settings: Settings, user_access_token: str) -> None:
    if settings.vk_group_id is None:
        raise ValueError("VK_GROUP_ID is not configured.")

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{VK_API_BASE_URL}/messages.allowMessagesFromGroup",
            data={
                "access_token": user_access_token,
                "v": settings.vk_api_version,
                "group_id": str(settings.vk_group_id),
            },
        )
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, dict):
        raise ValueError("VK allow messages response must be an object.")
    if "error" in payload:
        error = payload["error"]
        error_message = (
            error.get("error_msg", "VK API error") if isinstance(error, dict) else str(error)
        )
        raise ValueError(error_message)


def sign_state_payload(settings: Settings, encoded_payload: str) -> str:
    secret = vk_oauth_state_secret(settings)
    if not secret:
        raise ValueError("VK OAuth state secret is not configured.")
    digest = hmac.new(
        secret.encode(),
        encoded_payload.encode(),
        hashlib.sha256,
    ).digest()
    return base64url_encode(digest)


def vk_oauth_state_secret(settings: Settings) -> str | None:
    return settings.vk_oauth_state_secret or settings.vk_callback_secret


def build_code_verifier() -> str:
    return secrets.token_urlsafe(64)[:96]


def build_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode()).digest()
    return base64url_encode(digest)


def base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode())
