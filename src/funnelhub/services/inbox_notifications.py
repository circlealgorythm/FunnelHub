from __future__ import annotations

import logging
import uuid
from typing import Any, Protocol, cast

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.config import Settings
from funnelhub.db.models import Conversation, Lead, LeadContact, Message, MessengerIdentity

logger = logging.getLogger(__name__)


class TelegramNotificationClient(Protocol):
    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        *,
        disable_web_page_preview: bool | None = None,
    ) -> Any: ...


async def notify_admin_about_inbound_message(
    session: AsyncSession,
    *,
    settings: Settings,
    message: Message,
    client: TelegramNotificationClient | None = None,
) -> bool:
    if not is_inbox_notification_configured(settings):
        return False
    if message.lead_id is None:
        return False

    owns_client = client is None
    bot: Bot | None = None
    if client is None:
        if settings.inbox_notify_telegram_bot_token is None:
            return False
        bot = Bot(token=settings.inbox_notify_telegram_bot_token)
        client = bot

    try:
        text = await build_admin_notification_text(session, settings=settings, message=message)
        await client.send_message(
            chat_id=settings.inbox_notify_telegram_chat_id or "",
            text=text,
            disable_web_page_preview=True,
        )
        return True
    except Exception:
        logger.exception("Failed to send inbox Telegram notification")
        return False
    finally:
        if owns_client and bot is not None:
            await bot.session.close()


async def build_admin_notification_text(
    session: AsyncSession,
    *,
    settings: Settings,
    message: Message,
) -> str:
    if message.lead_id is None:
        return "Новое сообщение в Inbox"
    lead_id = message.lead_id
    lead = await session.get(Lead, message.lead_id)
    conversation = (
        await session.get(Conversation, message.conversation_id)
        if message.conversation_id is not None
        else None
    )
    identity = await get_identity(session, lead_id=lead_id, channel=message.channel)
    email = await get_contact_value(session, lead_id=lead_id, contact_type="email")
    phone = await get_contact_value(session, lead_id=lead_id, contact_type="phone")

    lead_name = get_lead_name(lead, identity)
    channel = channel_label(message.channel)
    contact_line = format_contact_line(email=email, phone=phone)
    preview = preview_text(message.body)
    inbox_link = build_inbox_link(settings, conversation.id if conversation else None)

    parts = [
        "Новое сообщение в Inbox",
        "",
        f"Канал: {channel}",
        f"Лид: {lead_name}",
    ]
    if contact_line:
        parts.append(f"Контакт: {contact_line}")
    parts.extend(
        [
            "",
            preview,
            "",
            f"Открыть Inbox: {inbox_link}",
        ]
    )
    return "\n".join(parts)


def is_inbox_notification_configured(settings: Settings) -> bool:
    return bool(
        settings.inbox_notify_telegram_bot_token
        and settings.inbox_notify_telegram_chat_id
    )


def build_inbox_link(settings: Settings, conversation_id: uuid.UUID | None) -> str:
    base_url = settings.inbox_app_url.rstrip("/")
    if conversation_id is None:
        return base_url
    return f"{base_url}?conversation={conversation_id}"


async def get_identity(
    session: AsyncSession,
    *,
    lead_id: uuid.UUID,
    channel: str,
) -> MessengerIdentity | None:
    return cast(
        MessengerIdentity | None,
        await session.scalar(
            select(MessengerIdentity).where(
                MessengerIdentity.lead_id == lead_id,
                MessengerIdentity.channel == channel,
            )
        ),
    )


async def get_contact_value(
    session: AsyncSession,
    *,
    lead_id: uuid.UUID,
    contact_type: str,
) -> str | None:
    return cast(
        str | None,
        await session.scalar(
        select(LeadContact.value)
        .where(
            LeadContact.lead_id == lead_id,
            LeadContact.contact_type == contact_type,
        )
        .order_by(LeadContact.is_primary.desc(), LeadContact.created_at.asc())
        .limit(1)
        ),
    )


def get_lead_name(lead: Lead | None, identity: MessengerIdentity | None) -> str:
    if lead is not None:
        lead_name = lead.full_name or " ".join(
            part for part in [lead.first_name, lead.last_name] if part
        )
        if lead_name:
            return lead_name
    if identity is not None:
        return identity.display_name or identity.username or "Без имени"
    return "Без имени"


def channel_label(channel: str) -> str:
    return {
        "telegram": "Telegram",
        "vk": "VK",
    }.get(channel, channel)


def preview_text(body: str | None, limit: int = 320) -> str:
    text = " ".join((body or "").split())
    if not text:
        return "Сообщение без текста."
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}..."


def format_contact_line(*, email: str | None, phone: str | None) -> str | None:
    contacts = [value for value in [email, phone] if value]
    if not contacts:
        return None
    return " · ".join(contacts)
