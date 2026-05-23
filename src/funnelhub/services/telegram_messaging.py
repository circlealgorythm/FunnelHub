from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.models import Message, MessengerIdentity


class TelegramMessageClient(Protocol):
    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> Any: ...


@dataclass(frozen=True)
class TelegramUrlButton:
    text: str
    url: str


@dataclass(frozen=True)
class TelegramSendResult:
    message_id: uuid.UUID
    external_message_id: str | None


async def send_telegram_text_message(
    session: AsyncSession,
    bot: TelegramMessageClient,
    lead_id: uuid.UUID,
    text: str,
    url_buttons: Sequence[TelegramUrlButton] | None = None,
) -> TelegramSendResult:
    identity = await get_subscribed_telegram_identity(session, lead_id)
    if identity is None:
        raise ValueError("Lead has no subscribed Telegram identity.")

    now = datetime.now(UTC)
    reply_markup = build_url_keyboard(url_buttons)
    metadata = build_message_metadata(url_buttons)
    message = Message(
        id=uuid.uuid4(),
        lead_id=lead_id,
        channel="telegram",
        direction="outbound",
        message_type="text",
        body=text,
        status="created",
        metadata_=metadata,
    )
    session.add(message)
    await session.flush()

    try:
        sent_message = await bot.send_message(
            chat_id=identity.external_user_id,
            text=text,
            reply_markup=reply_markup,
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
    return TelegramSendResult(
        message_id=message.id,
        external_message_id=external_message_id,
    )


async def get_subscribed_telegram_identity(
    session: AsyncSession,
    lead_id: uuid.UUID,
) -> MessengerIdentity | None:
    identity = await session.scalar(
        select(MessengerIdentity)
        .where(
            MessengerIdentity.lead_id == lead_id,
            MessengerIdentity.channel == "telegram",
            MessengerIdentity.is_subscribed.is_(True),
        )
        .order_by(MessengerIdentity.created_at.desc())
    )
    return identity


async def get_telegram_identity_by_user_id(
    session: AsyncSession,
    external_user_id: str,
) -> MessengerIdentity | None:
    identity = await session.scalar(
        select(MessengerIdentity).where(
            MessengerIdentity.channel == "telegram",
            MessengerIdentity.external_user_id == external_user_id,
        )
    )
    return identity


async def unsubscribe_telegram_identity(
    session: AsyncSession,
    external_user_id: str,
) -> bool:
    identity = await get_telegram_identity_by_user_id(session, external_user_id)
    if identity is None:
        return False

    identity.is_subscribed = False
    identity.unsubscribed_at = datetime.now(UTC)
    await session.flush()
    return True


def build_url_keyboard(
    url_buttons: Sequence[TelegramUrlButton] | None,
) -> InlineKeyboardMarkup | None:
    if not url_buttons:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button.text, url=button.url)] for button in url_buttons
        ]
    )


def build_message_metadata(
    url_buttons: Sequence[TelegramUrlButton] | None,
) -> dict[str, Any]:
    if not url_buttons:
        return {}
    return {
        "buttons": [
            {
                "type": "url",
                "text": button.text,
                "url": button.url,
            }
            for button in url_buttons
        ]
    }


def extract_external_message_id(sent_message: Any) -> str | None:
    message_id = getattr(sent_message, "message_id", None)
    if message_id is None:
        return None
    return str(message_id)
