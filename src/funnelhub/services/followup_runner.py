from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.models import (
    Conversation,
    FunnelFollowupDelivery,
    FunnelFollowupPost,
    MessengerIdentity,
)
from funnelhub.services.inbox import InboxSendClients
from funnelhub.services.telegram_messaging import send_telegram_text_message
from funnelhub.services.vk_messaging import send_vk_text_message

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FollowupRunStats:
    due: int = 0
    completed: int = 0
    failed: int = 0
    partial_failed: int = 0


async def run_due_followup_posts_once(
    session: AsyncSession,
    *,
    clients: InboxSendClients,
    limit: int = 50,
) -> FollowupRunStats:
    now = datetime.now(UTC)
    rows = (
        await session.execute(
            select(FunnelFollowupDelivery, FunnelFollowupPost)
            .join(
                FunnelFollowupPost,
                FunnelFollowupPost.id == FunnelFollowupDelivery.followup_post_id,
            )
            .where(
                FunnelFollowupPost.status != "cancelled",
                FunnelFollowupDelivery.status.in_(["pending", "failed"]),
                FunnelFollowupDelivery.available_at <= now,
            )
            .order_by(
                FunnelFollowupDelivery.available_at.asc(),
                FunnelFollowupDelivery.created_at.asc(),
            )
            .limit(limit)
        )
    ).all()
    if not rows:
        return FollowupRunStats()

    completed_count = 0
    failed_count = 0
    partial_count = 0
    posts_by_id: dict[uuid.UUID, FunnelFollowupPost] = {}

    for delivery, post in rows:
        post.status = "sending"
        posts_by_id[post.id] = post
        await session.flush()

        await send_one_delivery(
            session=session,
            post=post,
            delivery=delivery,
            clients=clients,
        )
        await session.flush()

    for post in posts_by_id.values():
        await refresh_post_status(session, post)
        if post.status == "completed":
            completed_count += 1
        elif post.status == "partial_failed":
            partial_count += 1
        elif post.status == "failed":
            failed_count += 1

    await session.commit()

    return FollowupRunStats(
        due=len(posts_by_id),
        completed=completed_count,
        failed=failed_count,
        partial_failed=partial_count,
    )


async def send_one_delivery(
    *,
    session: AsyncSession,
    post: FunnelFollowupPost,
    delivery: FunnelFollowupDelivery,
    clients: InboxSendClients,
) -> None:
    now = datetime.now(UTC)
    delivery.status = "sending"
    delivery.attempted_at = now
    delivery.error = None

    identity = await resolve_subscribed_identity(session, delivery)
    if identity is None:
        delivery.status = "skipped_unsubscribed"
        delivery.error = f"{delivery.channel}: unsubscribed or not linked"
        delivery.payload = {}
        await session.flush()
        return

    delivery.messenger_identity_id = identity.id
    conversation = await ensure_conversation(session, delivery.lead_id, delivery.channel)

    try:
        if delivery.channel == "telegram":
            if clients.telegram_bot is None:
                raise ValueError("Telegram client is not configured.")
            telegram_result = await send_telegram_text_message(
                session=session,
                bot=clients.telegram_bot,
                lead_id=delivery.lead_id,
                text=post.body,
            )
            message_id = telegram_result.message_id
            external_message_id = telegram_result.external_message_id
        elif delivery.channel == "vk":
            if clients.vk_client is None:
                raise ValueError("VK client is not configured.")
            vk_result = await send_vk_text_message(
                session=session,
                client=clients.vk_client,
                lead_id=delivery.lead_id,
                text=post.body,
            )
            message_id = vk_result.message_id
            external_message_id = vk_result.external_message_id
        else:
            raise ValueError(f"Unsupported follow-up channel: {delivery.channel}.")
    except Exception as exc:
        delivery.status = "failed"
        delivery.error = str(exc)
        delivery.payload = {}
        logger.warning(
            "Follow-up post %s failed to send to lead %s via %s: %s",
            post.id,
            delivery.lead_id,
            delivery.channel,
            exc,
        )
        await session.flush()
        return

    delivery.status = "sent"
    delivery.sent_at = now
    delivery.message_id = message_id
    delivery.external_message_id = external_message_id
    delivery.payload = {"conversation_id": str(conversation.id)}
    conversation.last_message_at = now
    await session.flush()


async def resolve_subscribed_identity(
    session: AsyncSession,
    delivery: FunnelFollowupDelivery,
) -> MessengerIdentity | None:
    if delivery.messenger_identity_id is not None:
        identity = await session.get(MessengerIdentity, delivery.messenger_identity_id)
        if (
            identity is not None
            and identity.channel == delivery.channel
            and identity.lead_id == delivery.lead_id
            and identity.is_subscribed
        ):
            return identity

    return cast(
        MessengerIdentity | None,
        await session.scalar(
            select(MessengerIdentity)
            .where(
                MessengerIdentity.lead_id == delivery.lead_id,
                MessengerIdentity.channel == delivery.channel,
                MessengerIdentity.is_subscribed.is_(True),
            )
            .order_by(MessengerIdentity.created_at.desc())
        ),
    )


async def ensure_conversation(
    session: AsyncSession,
    lead_id: uuid.UUID,
    channel: str,
) -> Conversation:
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.lead_id == lead_id,
            Conversation.channel == channel,
        )
    )
    if conversation is not None:
        return conversation

    conversation = Conversation(
        id=uuid.uuid4(),
        lead_id=lead_id,
        channel=channel,
        status="replied",
        last_message_at=datetime.now(UTC),
    )
    session.add(conversation)
    await session.flush()
    return conversation


async def refresh_post_status(
    session: AsyncSession,
    post: FunnelFollowupPost,
) -> None:
    rows = (
        await session.execute(
            select(FunnelFollowupDelivery.status, func.count())
            .where(FunnelFollowupDelivery.followup_post_id == post.id)
            .group_by(FunnelFollowupDelivery.status)
        )
    ).all()
    counts = {str(status): int(count) for status, count in rows}
    total = sum(counts.values())
    sent = counts.get("sent", 0)
    skipped = counts.get("skipped_unsubscribed", 0) + counts.get("cancelled", 0)
    failed = counts.get("failed", 0)
    pending = counts.get("pending", 0) + counts.get("sending", 0)

    post.total_deliveries = total
    post.sent_deliveries = sent
    post.skipped_deliveries = skipped
    post.failed_deliveries = failed

    if total == 0:
        post.status = "completed"
        post.completed_at = datetime.now(UTC)
    elif pending:
        post.status = "partial_failed" if failed else "queued"
    elif failed and (sent or skipped):
        post.status = "partial_failed"
    elif failed:
        post.status = "failed"
    else:
        post.status = "completed"
        post.completed_at = datetime.now(UTC)
    await session.flush()
