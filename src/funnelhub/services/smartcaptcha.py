from __future__ import annotations

import logging

import httpx

SMARTCAPTCHA_VALIDATE_URL = "https://smartcaptcha.cloud.yandex.ru/validate"
logger = logging.getLogger(__name__)


class SmartCaptchaUnavailableError(RuntimeError):
    """Raised when SmartCaptcha cannot be used to verify a submission."""


async def verify_smartcaptcha_token(
    *,
    server_key: str | None,
    token: str,
    client_ip: str | None,
) -> bool:
    """Return whether a one-time SmartCaptcha token belongs to a human visitor."""
    if not server_key:
        raise SmartCaptchaUnavailableError("SmartCaptcha server key is not configured.")

    form_data = {"secret": server_key, "token": token}
    if client_ip:
        form_data["ip"] = client_ip

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(SMARTCAPTCHA_VALIDATE_URL, data=form_data)
    except httpx.HTTPError as exc:
        raise SmartCaptchaUnavailableError("SmartCaptcha validation request failed.") from exc

    if response.status_code != httpx.codes.OK:
        logger.warning("SmartCaptcha validation returned HTTP %s.", response.status_code)
        raise SmartCaptchaUnavailableError("SmartCaptcha validation returned an unexpected status.")

    try:
        payload = response.json()
    except ValueError as exc:
        raise SmartCaptchaUnavailableError(
            "SmartCaptcha validation returned invalid JSON."
        ) from exc

    return isinstance(payload, dict) and payload.get("status") == "ok"
