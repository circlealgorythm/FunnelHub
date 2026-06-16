from __future__ import annotations

import json
import random
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.models import Conversation, Message, MessengerIdentity

VK_BUTTON_LABEL_MAX_LENGTH = 40


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

    async def publish_wall_post(
        self,
        *,
        owner_id: int | None,
        message: str,
        attachments: Sequence[str] | None = None,
        from_group: bool = True,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "access_token": self._access_token,
            "v": self._api_version,
            "message": message,
        }
        if owner_id is not None:
            data["owner_id"] = str(owner_id)
        if from_group:
            data["from_group"] = "1"
        if attachments:
            data["attachments"] = ",".join(attachments)
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(f"{self._base_url}/wall.post", data=data)
            response.raise_for_status()
            payload = cast(dict[str, Any], response.json())

        if "error" in payload:
            error = payload["error"]
            error_message = (
                error.get("error_msg", "VK API error") if isinstance(error, dict) else str(error)
            )
            raise RuntimeError(error_message)
        return payload

    async def upload_wall_photo(
        self,
        *,
        owner_id: int | None,
        image_path: Path,
    ) -> str:
        group_id = abs(owner_id) if owner_id is not None and owner_id < 0 else None
        upload_server_data: dict[str, Any] = {
            "access_token": self._access_token,
            "v": self._api_version,
        }
        if group_id is not None:
            upload_server_data["group_id"] = str(group_id)

        async with httpx.AsyncClient(timeout=30.0) as client:
            upload_server_response = await client.post(
                f"{self._base_url}/photos.getWallUploadServer",
                data=upload_server_data,
            )
            upload_server_response.raise_for_status()
            upload_server_payload = cast(dict[str, Any], upload_server_response.json())
            if "error" in upload_server_payload:
                raise RuntimeError(format_vk_error(upload_server_payload["error"]))

            response_data = upload_server_payload.get("response")
            if not isinstance(response_data, dict) or not response_data.get("upload_url"):
                raise RuntimeError("VK did not return a wall photo upload URL.")

            upload_url = str(response_data["upload_url"])
            with image_path.open("rb") as image_file:
                upload_response = await client.post(
                    upload_url,
                    files={"photo": (image_path.name, image_file)},
                )
            upload_response.raise_for_status()
            upload_payload = cast(dict[str, Any], upload_response.json())

            save_data: dict[str, Any] = {
                "access_token": self._access_token,
                "v": self._api_version,
                "photo": upload_payload["photo"],
                "server": str(upload_payload["server"]),
                "hash": upload_payload["hash"],
            }
            if group_id is not None:
                save_data["group_id"] = str(group_id)

            save_response = await client.post(
                f"{self._base_url}/photos.saveWallPhoto",
                data=save_data,
            )
            save_response.raise_for_status()
            save_payload = cast(dict[str, Any], save_response.json())
            if "error" in save_payload:
                raise RuntimeError(format_vk_error(save_payload["error"]))

        saved_photos = save_payload.get("response")
        if not isinstance(saved_photos, list) or not saved_photos:
            raise RuntimeError("VK did not return saved wall photo metadata.")
        saved_photo = saved_photos[0]
        if not isinstance(saved_photo, dict):
            raise RuntimeError("VK returned invalid wall photo metadata.")
        photo_owner_id = saved_photo.get("owner_id")
        photo_id = saved_photo.get("id")
        if photo_owner_id is None or photo_id is None:
            raise RuntimeError("VK saved wall photo metadata has no owner_id/id.")
        return f"photo{photo_owner_id}_{photo_id}"


def format_vk_error(error: Any) -> str:
    if isinstance(error, dict):
        return str(error.get("error_msg", "VK API error"))
    return str(error)


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
    conversation = await get_latest_vk_conversation(session, lead_id)
    if conversation is not None:
        conversation.last_message_at = now
    message = Message(
        id=uuid.uuid4(),
        lead_id=lead_id,
        conversation_id=conversation.id if conversation is not None else None,
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


async def get_latest_vk_conversation(
    session: AsyncSession,
    lead_id: uuid.UUID,
) -> Conversation | None:
    return cast(
        Conversation | None,
        await session.scalar(
            select(Conversation)
            .where(
                Conversation.lead_id == lead_id,
                Conversation.channel == "vk",
            )
            .order_by(Conversation.updated_at.desc())
        )
    )


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
                    **build_button_style(button),
                }
            ]
            for button in url_buttons
        ],
    }


def build_button_action(button: VkButton) -> dict[str, str]:
    if isinstance(button, VkUrlButton):
        return {
            "type": "open_link",
            "label": normalize_vk_button_label(button.text),
            "link": button.url,
        }
    return {
        "type": "text",
        "label": normalize_vk_button_label(button.text),
    }


def normalize_vk_button_label(text: str) -> str:
    return text[:VK_BUTTON_LABEL_MAX_LENGTH]


def build_button_style(button: VkButton) -> dict[str, str]:
    if isinstance(button, VkTextButton):
        return {"color": "primary"}
    return {}


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
