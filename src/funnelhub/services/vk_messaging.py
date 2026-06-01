from __future__ import annotations

import json
import random
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.models import Message, MessengerIdentity


class VkMessageClient(Protocol):
    async def send_message(
        self,
        peer_id: int | str,
        message: str,
        *,
        keyboard: dict[str, Any] | None = None,
    ) -> Any: ...


class HttpVkMessageClient:
    def __init__(
        self,
        access_token: str,
        api_version: str,
        base_url: str = "https://api.vk.com/method",
    ) -> None:
        self._access_token = access_token
        self._api_version = api_version
        self._base_url = base_url.rstrip("/")

    async def send_message(
        self,
        peer_id: int | str,
        message: str,
        *,
        keyboard: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "access_token": self._access_token,
            "v": self._api_version,
            "peer_id": str(peer_id),
            "message": message,
            "random_id": random.randint(1, 2_147_483_647),
        }
        if keyboard is not None:
            data["keyboard"] = json.dumps(keyboard, ensure_ascii=False)

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(f"{self._base_url}/messages.send", data=data)
            response.raise_for_status()
            payload = cast(dict[str, Any], response.json())

        if "error" in payload:
            error = payload["error"]
            error_message = (
                error.get("error_msg", "VK API error") if isinstance(error, dict) else str(error)
            )
            raise RuntimeError(error_message)
        return payload


@dataclass(frozen=True)
class VkUrlButton:
    text: str
    url: str


@dataclass(frozen=True)
class VkTextButton:
    text: str


VkButton = VkUrlButton | VkTextButton


@dataclass(frozen=True)
class VkSendResult:
    message_id: uuid.UUID
    external_message_id: str | None


async def send_vk_text_message(
    session: AsyncSession,
    client: VkMessageClient,
    lead_id: uuid.UUID,
    text: str,
    url_buttons: Sequence[VkButton] | None = None,
) -> VkSendResult:
    identity = await get_subscribed_vk_identity(session, lead_id)
    if identity is None:
        raise ValueError("Lead has no subscribed VK identity.")

    now = datetime.now(UTC)
    keyboard = build_url_keyboard(url_buttons)
    metadata = build_message_metadata(url_buttons)
    message = Message(
        id=uuid.uuid4(),
        lead_id=lead_id,
        channel="vk",
        direction="outbound",
        message_type="text",
        body=text,
        status="created",
        metadata_=metadata,
    )
    session.add(message)
    await session.flush()

    try:
        sent_message = await client.send_message(
            peer_id=identity.external_user_id,
            message=text,
            keyboard=keyboard,
        )
    except Exception as exc:
        message.status = "failed"
        message.metadata_ = {**metadata, "error": str(exc)}
        await session.flush()
        raise

    external_message_id = extract_external_message_id(sent_message)
    message.external_message_id = external_message_id
    message.status = "sent"
    message.sent_at = now
    await session.flush()
    return VkSendResult(
        message_id=message.id,
        external_message_id=external_message_id,
    )


async def get_subscribed_vk_identity(
    session: AsyncSession,
    lead_id: uuid.UUID,
) -> MessengerIdentity | None:
    identity = await session.scalar(
        select(MessengerIdentity)
        .where(
            MessengerIdentity.lead_id == lead_id,
            MessengerIdentity.channel == "vk",
            MessengerIdentity.is_subscribed.is_(True),
        )
        .order_by(MessengerIdentity.created_at.desc())
    )
    return identity


async def get_vk_identity_by_user_id(
    session: AsyncSession,
    external_user_id: str,
) -> MessengerIdentity | None:
    identity = await session.scalar(
        select(MessengerIdentity).where(
            MessengerIdentity.channel == "vk",
            MessengerIdentity.external_user_id == external_user_id,
        )
    )
    return identity


async def unsubscribe_vk_identity(
    session: AsyncSession,
    external_user_id: str,
) -> bool:
    identity = await get_vk_identity_by_user_id(session, external_user_id)
    if identity is None:
        return False

    identity.is_subscribed = False
    identity.unsubscribed_at = datetime.now(UTC)
    await session.flush()
    return True


def build_url_keyboard(url_buttons: Sequence[VkButton] | None) -> dict[str, Any] | None:
    if not url_buttons:
        return None
    return {
        "one_time": False,
        "inline": True,
        "buttons": [
            [
                {
                    "action": build_button_action(button),
                }
            ]
            for button in url_buttons
        ],
    }


def build_button_action(button: VkButton) -> dict[str, str]:
    if isinstance(button, VkUrlButton):
        return {
            "type": "open_link",
            "label": button.text,
            "link": button.url,
        }
    return {
        "type": "text",
        "label": button.text,
    }


def build_message_metadata(url_buttons: Sequence[VkButton] | None) -> dict[str, Any]:
    if not url_buttons:
        return {}
    return {
        "buttons": [
            {
                "type": "url" if isinstance(button, VkUrlButton) else "text",
                "text": button.text,
                "url": button.url if isinstance(button, VkUrlButton) else None,
            }
            for button in url_buttons
        ]
    }


def extract_external_message_id(sent_message: Any) -> str | None:
    if not isinstance(sent_message, dict):
        return None

    response = sent_message.get("response")
    if isinstance(response, int | str):
        return str(response)
    if isinstance(response, list) and response:
        return str(response[0])
    return None
