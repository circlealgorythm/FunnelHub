from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.models import Conversation, Message, MessengerIdentity


class TelegramMessageClient(Protocol):
    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        *,
        reply_markup: Any | None = None,
    ) -> Any: ...


@dataclass(frozen=True)
class TelegramUrlButton:
    text: str
    url: str


@dataclass(frozen=True)
class TelegramTextButton:
    text: str


TelegramButton = TelegramUrlButton | TelegramTextButton
TEXT_CALLBACK_PREFIX = "fh_answer:"
MAX_CALLBACK_DATA_BYTES = 64


@dataclass(frozen=True)
class TelegramSendResult:
    message_id: uuid.UUID
    external_message_id: str | None


async def send_telegram_text_message(
    session: AsyncSession,
    bot: TelegramMessageClient,
    lead_id: uuid.UUID,
    text: str,
    url_buttons: Sequence[TelegramButton] | None = None,
) -> TelegramSendResult:
    identity = await get_subscribed_telegram_identity(session, lead_id)
    if identity is None:
        raise ValueError("Lead has no subscribed Telegram identity.")

    now = datetime.now(UTC)
    reply_markup = build_url_keyboard(url_buttons)
    metadata = build_message_metadata(url_buttons)
    conversation = await get_latest_telegram_conversation(session, lead_id)
    if conversation is not None:
        conversation.last_message_at = now
    message = Message(
        id=uuid.uuid4(),
        lead_id=lead_id,
        conversation_id=conversation.id if conversation is not None else None,
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


async def get_latest_telegram_conversation(
    session: AsyncSession,
    lead_id: uuid.UUID,
) -> Conversation | None:
    return cast(
        Conversation | None,
        await session.scalar(
            select(Conversation)
            .where(
                Conversation.lead_id == lead_id,
                Conversation.channel == "telegram",
            )
            .order_by(Conversation.updated_at.desc())
        )
    )


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
    url_buttons: Sequence[TelegramButton] | None,
) -> InlineKeyboardMarkup | None:
    if not url_buttons:
        return None

    inline_keyboard: list[list[InlineKeyboardButton]] = []
    for button in url_buttons:
        if isinstance(button, TelegramUrlButton):
            inline_keyboard.append([InlineKeyboardButton(text=button.text, url=button.url)])
            continue

        callback_data = build_text_callback_data(button.text)
        if callback_data is None:
            return None
        inline_keyboard.append(
            [InlineKeyboardButton(text=button.text, callback_data=callback_data)]
        )

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def build_text_callback_data(text: str) -> str | None:
    callback_data = f"{TEXT_CALLBACK_PREFIX}{text}"
    if len(callback_data.encode()) > MAX_CALLBACK_DATA_BYTES:
        return None
    return callback_data


def parse_text_callback_data(callback_data: str) -> str | None:
    if not callback_data.startswith(TEXT_CALLBACK_PREFIX):
        return None
    text = callback_data[len(TEXT_CALLBACK_PREFIX) :].strip()
    return text or None


def build_message_metadata(
    url_buttons: Sequence[TelegramButton] | None,
) -> dict[str, Any]:
    if not url_buttons:
        return {}
    return {
        "buttons": [
            {
                "type": "url" if isinstance(button, TelegramUrlButton) else "text",
                "text": button.text,
                "url": button.url if isinstance(button, TelegramUrlButton) else None,
            }
            for button in url_buttons
        ]
    }


def extract_external_message_id(sent_message: Any) -> str | None:
    message_id = getattr(sent_message, "message_id", None)
    if message_id is None:
        return None
    return str(message_id)
