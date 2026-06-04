from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, cast

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.models import (
    Conversation,
    EmailSubscription,
    Lead,
    LeadContact,
    Message,
    MessengerIdentity,
)
from funnelhub.services.email_messaging import EmailProviderClient, send_email_text_message
from funnelhub.services.telegram_messaging import TelegramMessageClient, send_telegram_text_message
from funnelhub.services.vk_messaging import VkMessageClient, send_vk_text_message

ReplyChannel = Literal["telegram", "vk", "email"]
SUPPORTED_REPLY_CHANNELS: tuple[ReplyChannel, ...] = ("telegram", "vk", "email")


class InboxSendClients(Protocol):
    telegram_bot: TelegramMessageClient | None
    vk_client: VkMessageClient | None
    email_client: EmailProviderClient | None
    email_subject: str
    public_base_url: str
    email_from_email: str | None
    email_from_name: str | None
    email_signature_image_url: str | None


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
class InboxReplyChannelOption:
    channel: ReplyChannel
    label: str
    detail: str | None
    is_default: bool


@dataclass(frozen=True)
class InboxConversationDetail:
    conversation: InboxConversationSummary
    messages: list[InboxMessageView]
    reply_channels: list[InboxReplyChannelOption]


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
    channels: list[ReplyChannel] | None = None,
) -> list[Message]:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise ValueError("Conversation not found.")

    clean_text = text.strip()
    if not clean_text:
        raise ValueError("Reply text is required.")

    reply_channels = normalize_reply_channels(channels, fallback_channel=conversation.channel)
    await validate_reply_channels(
        session=session,
        lead_id=conversation.lead_id,
        channels=reply_channels,
    )

    sent_messages: list[Message] = []
    for channel in reply_channels:
        message = await send_reply_to_channel(
            session=session,
            conversation=conversation,
            channel=channel,
            text=clean_text,
            clients=clients,
        )
        message.conversation_id = conversation.id
        sent_messages.append(message)

    conversation.status = "replied"
    conversation.last_message_at = max(
        (message.sent_at for message in sent_messages if message.sent_at is not None),
        default=datetime.now(UTC),
    )
    await session.flush()
    return sent_messages


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
        reply_channels=await get_available_reply_channels(
            session=session,
            lead_id=row.lead_id,
            current_channel=row.channel,
        ),
    )


async def send_reply_to_channel(
    *,
    session: AsyncSession,
    conversation: Conversation,
    channel: ReplyChannel,
    text: str,
    clients: InboxSendClients,
) -> Message:
    message_id: uuid.UUID
    if channel == "telegram":
        if clients.telegram_bot is None:
            raise ValueError("Telegram client is not configured.")
        telegram_result = await send_telegram_text_message(
            session=session,
            bot=clients.telegram_bot,
            lead_id=conversation.lead_id,
            text=text,
        )
        message_id = telegram_result.message_id
    elif channel == "vk":
        if clients.vk_client is None:
            raise ValueError("VK client is not configured.")
        vk_result = await send_vk_text_message(
            session=session,
            client=clients.vk_client,
            lead_id=conversation.lead_id,
            text=text,
        )
        message_id = vk_result.message_id
    else:
        if clients.email_client is None:
            raise ValueError("Email client is not configured.")
        email_result = await send_email_text_message(
            session=session,
            client=clients.email_client,
            lead_id=conversation.lead_id,
            subject=clients.email_subject,
            text=text,
            public_base_url=clients.public_base_url,
            from_email=clients.email_from_email,
            from_name=clients.email_from_name,
            signature_image_url=clients.email_signature_image_url,
            metadata={"source": "inbox_manual_reply"},
        )
        message_id = email_result.message_id

    message = await session.get(Message, message_id)
    if message is None:
        raise RuntimeError("Outbound message was not persisted.")
    return message


async def validate_reply_channels(
    *,
    session: AsyncSession,
    lead_id: uuid.UUID,
    channels: list[ReplyChannel],
) -> None:
    available_channels = {
        option.channel
        for option in await get_available_reply_channels(
            session=session,
            lead_id=lead_id,
            current_channel=None,
        )
    }
    missing_channels = [channel for channel in channels if channel not in available_channels]
    if missing_channels:
        raise ValueError(f"Reply channel is not available: {', '.join(missing_channels)}")


async def get_available_reply_channels(
    *,
    session: AsyncSession,
    lead_id: uuid.UUID,
    current_channel: str | None,
) -> list[InboxReplyChannelOption]:
    options: list[InboxReplyChannelOption] = []
    identities = (
        await session.scalars(
            select(MessengerIdentity)
            .where(
                MessengerIdentity.lead_id == lead_id,
                MessengerIdentity.channel.in_(("telegram", "vk")),
                MessengerIdentity.is_subscribed.is_(True),
            )
            .order_by(MessengerIdentity.created_at.desc())
        )
    ).all()
    seen_channels: set[str] = set()
    for identity in identities:
        if identity.channel in seen_channels:
            continue
        seen_channels.add(identity.channel)
        channel = cast(ReplyChannel, identity.channel)
        options.append(
            InboxReplyChannelOption(
                channel=channel,
                label=channel_label(channel),
                detail=identity.username or identity.display_name or identity.external_user_id,
                is_default=identity.channel == current_channel,
            )
        )

    subscription = await get_subscribed_email_subscription(session, lead_id)
    if subscription is not None:
        options.append(
            InboxReplyChannelOption(
                channel="email",
                label=channel_label("email"),
                detail=subscription.email,
                is_default=current_channel == "email",
            )
        )

    if not any(option.is_default for option in options) and options:
        options[0] = InboxReplyChannelOption(
            channel=options[0].channel,
            label=options[0].label,
            detail=options[0].detail,
            is_default=True,
        )
    return options


async def get_subscribed_email_subscription(
    session: AsyncSession,
    lead_id: uuid.UUID,
) -> EmailSubscription | None:
    return cast(
        EmailSubscription | None,
        await session.scalar(
            select(EmailSubscription)
            .where(
                EmailSubscription.lead_id == lead_id,
                EmailSubscription.status == "subscribed",
                EmailSubscription.unsubscribed_at.is_(None),
            )
            .order_by(EmailSubscription.created_at.desc())
        )
    )


def normalize_reply_channels(
    channels: list[ReplyChannel] | None,
    *,
    fallback_channel: str,
) -> list[ReplyChannel]:
    raw_channels = channels or [cast(ReplyChannel, fallback_channel)]
    normalized: list[ReplyChannel] = []
    for channel in raw_channels:
        if channel not in SUPPORTED_REPLY_CHANNELS:
            raise ValueError(f"Unsupported inbox channel: {channel}")
        if channel not in normalized:
            normalized.append(channel)
    if not normalized:
        raise ValueError("At least one reply channel is required.")
    return normalized


def channel_label(channel: ReplyChannel) -> str:
    return {
        "telegram": "Telegram",
        "vk": "VK",
        "email": "Email",
    }[channel]


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
