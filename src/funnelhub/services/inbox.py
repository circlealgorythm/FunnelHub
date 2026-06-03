from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.models import Conversation, Lead, LeadContact, Message, MessengerIdentity
from funnelhub.services.telegram_messaging import TelegramMessageClient, send_telegram_text_message
from funnelhub.services.vk_messaging import VkMessageClient, send_vk_text_message


class InboxSendClients(Protocol):
    telegram_bot: TelegramMessageClient | None
    vk_client: VkMessageClient | None


@dataclass(frozen=True)
class InboxConversationSummary:
    id: uuid.UUID
    lead_id: uuid.UUID
    channel: str
    status: str
    last_message_at: datetime | None
    lead_name: str | None
    lead_status: str
    email: str | None
    phone: str | None
    identity_display_name: str | None
    identity_username: str | None
    is_subscribed: bool | None
    last_message_body: str | None
    last_message_direction: str | None
    unread_count: int


@dataclass(frozen=True)
class InboxMessageView:
    id: uuid.UUID
    channel: str
    direction: str
    message_type: str
    body: str | None
    status: str
    created_at: datetime
    sent_at: datetime | None
    metadata: dict[str, Any]


@dataclass(frozen=True)
class InboxConversationDetail:
    conversation: InboxConversationSummary
    messages: list[InboxMessageView]


async def record_inbound_messenger_message(
    session: AsyncSession,
    *,
    channel: str,
    external_user_id: str,
    body: str,
    external_message_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    needs_reply: bool = True,
) -> Message | None:
    identity = await get_identity(session, channel=channel, external_user_id=external_user_id)
    if identity is None:
        return None

    now = datetime.now(UTC)
    conversation = await get_or_create_conversation(
        session=session,
        lead_id=identity.lead_id,
        channel=channel,
    )
    conversation.last_message_at = now
    if needs_reply:
        conversation.status = "needs_reply"

    message = Message(
        id=uuid.uuid4(),
        lead_id=identity.lead_id,
        conversation_id=conversation.id,
        channel=channel,
        direction="inbound",
        message_type="text",
        body=body,
        external_message_id=external_message_id,
        status="received",
        sent_at=now,
        metadata_=metadata or {},
    )
    session.add(message)
    await session.flush()
    return message


async def mark_conversation_auto_handled(
    session: AsyncSession,
    *,
    channel: str,
    external_user_id: str,
) -> None:
    identity = await get_identity(session, channel=channel, external_user_id=external_user_id)
    if identity is None:
        return

    conversation = await get_latest_conversation(
        session=session,
        lead_id=identity.lead_id,
        channel=channel,
    )
    if conversation is not None and conversation.status == "needs_reply":
        conversation.status = "open"
        await session.flush()


async def send_inbox_reply(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    text: str,
    clients: InboxSendClients,
) -> Message:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise ValueError("Conversation not found.")

    clean_text = text.strip()
    if not clean_text:
        raise ValueError("Reply text is required.")

    message_id: uuid.UUID
    if conversation.channel == "telegram":
        if clients.telegram_bot is None:
            raise ValueError("Telegram client is not configured.")
        telegram_result = await send_telegram_text_message(
            session=session,
            bot=clients.telegram_bot,
            lead_id=conversation.lead_id,
            text=clean_text,
        )
        message_id = telegram_result.message_id
    elif conversation.channel == "vk":
        if clients.vk_client is None:
            raise ValueError("VK client is not configured.")
        vk_result = await send_vk_text_message(
            session=session,
            client=clients.vk_client,
            lead_id=conversation.lead_id,
            text=clean_text,
        )
        message_id = vk_result.message_id
    else:
        raise ValueError(f"Unsupported inbox channel: {conversation.channel}")

    message = await session.get(Message, message_id)
    if message is None:
        raise RuntimeError("Outbound message was not persisted.")

    conversation.status = "replied"
    conversation.last_message_at = message.sent_at or datetime.now(UTC)
    message.conversation_id = conversation.id
    await session.flush()
    return message


async def list_inbox_conversations(
    session: AsyncSession,
    *,
    status: str | None = None,
) -> list[InboxConversationSummary]:
    statement = build_conversation_summary_query()
    if status:
        statement = statement.where(Conversation.status == status)
    statement = statement.order_by(
        Conversation.last_message_at.desc().nullslast(),
        Conversation.updated_at.desc(),
    )
    rows = (await session.execute(statement)).all()
    return [row_to_summary(row) for row in rows]


async def get_inbox_conversation_detail(
    session: AsyncSession,
    conversation_id: uuid.UUID,
) -> InboxConversationDetail | None:
    statement = build_conversation_summary_query().where(Conversation.id == conversation_id)
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        return None

    messages = (
        await session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
    ).all()
    return InboxConversationDetail(
        conversation=row_to_summary(row),
        messages=[
            InboxMessageView(
                id=message.id,
                channel=message.channel,
                direction=message.direction,
                message_type=message.message_type,
                body=message.body,
                status=message.status,
                created_at=message.created_at,
                sent_at=message.sent_at,
                metadata=message.metadata_ or {},
            )
            for message in messages
        ],
    )


async def get_identity(
    session: AsyncSession,
    *,
    channel: str,
    external_user_id: str,
) -> MessengerIdentity | None:
    return cast(
        MessengerIdentity | None,
        await session.scalar(
            select(MessengerIdentity).where(
                MessengerIdentity.channel == channel,
                MessengerIdentity.external_user_id == external_user_id,
            )
        )
    )


async def get_or_create_conversation(
    session: AsyncSession,
    *,
    lead_id: uuid.UUID,
    channel: str,
) -> Conversation:
    conversation = await get_latest_conversation(session=session, lead_id=lead_id, channel=channel)
    if conversation is not None:
        return conversation

    conversation = Conversation(
        id=uuid.uuid4(),
        lead_id=lead_id,
        channel=channel,
        status="open",
    )
    session.add(conversation)
    await session.flush()
    await session.execute(
        update(Message)
        .where(
            Message.lead_id == lead_id,
            Message.channel == channel,
            Message.conversation_id.is_(None),
        )
        .values(conversation_id=conversation.id)
    )
    return conversation


async def get_latest_conversation(
    session: AsyncSession,
    *,
    lead_id: uuid.UUID,
    channel: str,
) -> Conversation | None:
    return cast(
        Conversation | None,
        await session.scalar(
            select(Conversation)
            .where(
                Conversation.lead_id == lead_id,
                Conversation.channel == channel,
            )
            .order_by(Conversation.updated_at.desc())
        )
    )


def build_conversation_summary_query() -> Select[tuple[Any, ...]]:
    latest_message_created_at = (
        select(func.max(Message.created_at))
        .where(Message.conversation_id == Conversation.id)
        .correlate(Conversation)
        .scalar_subquery()
    )
    last_message_body = (
        select(Message.body)
        .where(
            Message.conversation_id == Conversation.id,
            Message.created_at == latest_message_created_at,
        )
        .order_by(Message.id.desc())
        .limit(1)
        .correlate(Conversation)
        .scalar_subquery()
    )
    last_message_direction = (
        select(Message.direction)
        .where(
            Message.conversation_id == Conversation.id,
            Message.created_at == latest_message_created_at,
        )
        .order_by(Message.id.desc())
        .limit(1)
        .correlate(Conversation)
        .scalar_subquery()
    )
    email = primary_contact_subquery("email")
    phone = primary_contact_subquery("phone")
    unread_count = (
        select(func.count(Message.id))
        .where(
            Message.conversation_id == Conversation.id,
            Message.direction == "inbound",
            Message.read_at.is_(None),
        )
        .correlate(Conversation)
        .scalar_subquery()
    )

    return (
        select(
            Conversation.id,
            Conversation.lead_id,
            Conversation.channel,
            Conversation.status,
            Conversation.last_message_at,
            Lead.full_name,
            Lead.first_name,
            Lead.last_name,
            Lead.status.label("lead_status"),
            email.label("email"),
            phone.label("phone"),
            MessengerIdentity.display_name,
            MessengerIdentity.username,
            MessengerIdentity.is_subscribed,
            last_message_body.label("last_message_body"),
            last_message_direction.label("last_message_direction"),
            unread_count.label("unread_count"),
        )
        .join(Lead, Lead.id == Conversation.lead_id)
        .outerjoin(
            MessengerIdentity,
            (MessengerIdentity.lead_id == Conversation.lead_id)
            & (MessengerIdentity.channel == Conversation.channel),
        )
    )


def primary_contact_subquery(contact_type: str) -> Any:
    return (
        select(LeadContact.value)
        .where(
            LeadContact.lead_id == Conversation.lead_id,
            LeadContact.contact_type == contact_type,
        )
        .order_by(LeadContact.is_primary.desc(), LeadContact.created_at.asc())
        .limit(1)
        .correlate(Conversation)
        .scalar_subquery()
    )


def row_to_summary(row: Any) -> InboxConversationSummary:
    lead_name = row.full_name or " ".join(
        part for part in [row.first_name, row.last_name] if part
    )
    return InboxConversationSummary(
        id=row.id,
        lead_id=row.lead_id,
        channel=row.channel,
        status=row.status,
        last_message_at=row.last_message_at,
        lead_name=lead_name or None,
        lead_status=row.lead_status,
        email=row.email,
        phone=row.phone,
        identity_display_name=row.display_name,
        identity_username=row.username,
        is_subscribed=row.is_subscribed,
        last_message_body=row.last_message_body,
        last_message_direction=row.last_message_direction,
        unread_count=int(row.unread_count or 0),
    )
