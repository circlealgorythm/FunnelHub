from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.models import (
    FunnelFollowupDelivery,
    FunnelFollowupPost,
    FunnelState,
    Lead,
    MessengerIdentity,
)

SUPPORTED_FOLLOWUP_CHANNELS = ("telegram", "vk")
FOLLOWUP_FUNNEL_KEY = "aisu_consultation"


@dataclass(frozen=True)
class FollowupDeliveryView:
    id: uuid.UUID
    lead_id: uuid.UUID
    lead_name: str | None
    channel: str
    status: str
    external_message_id: str | None
    attempted_at: datetime | None
    sent_at: datetime | None
    error: str | None


@dataclass(frozen=True)
class FollowupDetail:
    post: FunnelFollowupPost
    deliveries: list[FollowupDeliveryView]


@dataclass(frozen=True)
class FollowupRecipientPreview:
    total: int
    by_channel: dict[str, int]


async def create_followup_post(
    session: AsyncSession,
    *,
    title: str,
    body: str,
    channels: Sequence[str],
    scheduled_at: datetime | None = None,
    source_type: str = "manual",
    source_autopost_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> FunnelFollowupPost:
    clean_title = title.strip()
    clean_body = body.strip()
    clean_channels = normalize_followup_channels(channels)
    clean_source_type = source_type.strip() or "manual"

    if not clean_title:
        raise ValueError("Title is required.")
    if not clean_body:
        raise ValueError("Post body is required.")
    if clean_source_type not in {"manual", "autopost"}:
        raise ValueError(f"Unsupported follow-up source type: {clean_source_type}.")

    send_at = normalize_schedule(scheduled_at)
    status = "queued" if send_at <= datetime.now(UTC) else "scheduled"
    key = dedupe_key.strip() if dedupe_key and dedupe_key.strip() else build_followup_dedupe_key(
        body=clean_body,
        channels=clean_channels,
        scheduled_at=send_at,
        source_type=clean_source_type,
        source_autopost_id=source_autopost_id,
    )
    existing = await session.scalar(
        select(FunnelFollowupPost).where(FunnelFollowupPost.dedupe_key == key)
    )
    if existing is not None:
        return existing

    post = FunnelFollowupPost(
        id=uuid.uuid4(),
        title=clean_title,
        body=clean_body,
        channels=list(clean_channels),
        status=status,
        source_type=clean_source_type,
        source_autopost_id=source_autopost_id,
        dedupe_key=key,
        scheduled_at=send_at,
        metadata_=metadata or {},
    )
    session.add(post)
    await session.flush()

    deliveries = await build_followup_deliveries(session, post=post, channels=clean_channels)
    session.add_all(deliveries)
    post.total_deliveries = len(deliveries)
    if not deliveries:
        post.status = "completed"
        post.completed_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(post)
    return post


async def build_followup_deliveries(
    session: AsyncSession,
    *,
    post: FunnelFollowupPost,
    channels: Sequence[str],
) -> list[FunnelFollowupDelivery]:
    completed_lead_ids = select(distinct(FunnelState.lead_id)).where(
        FunnelState.funnel_key == FOLLOWUP_FUNNEL_KEY,
        FunnelState.status == "completed",
        FunnelState.completed_at.is_not(None),
    )
    identities = list(
        (
            await session.scalars(
                select(MessengerIdentity)
                .where(
                    MessengerIdentity.lead_id.in_(completed_lead_ids),
                    MessengerIdentity.channel.in_(channels),
                    MessengerIdentity.is_subscribed.is_(True),
                )
                .order_by(
                    MessengerIdentity.lead_id.asc(),
                    MessengerIdentity.channel.asc(),
                    MessengerIdentity.created_at.desc(),
                )
            )
        ).all()
    )

    deliveries: list[FunnelFollowupDelivery] = []
    seen: set[tuple[uuid.UUID, str]] = set()
    for identity in identities:
        key = (identity.lead_id, identity.channel)
        if key in seen:
            continue
        seen.add(key)
        deliveries.append(
            FunnelFollowupDelivery(
                id=uuid.uuid4(),
                followup_post_id=post.id,
                lead_id=identity.lead_id,
                channel=identity.channel,
                messenger_identity_id=identity.id,
                status="pending",
                payload={},
            )
        )
    return deliveries


async def preview_followup_recipients(
    session: AsyncSession,
    channels: Sequence[str],
) -> FollowupRecipientPreview:
    clean_channels = normalize_followup_channels(channels)
    completed_lead_ids = select(distinct(FunnelState.lead_id)).where(
        FunnelState.funnel_key == FOLLOWUP_FUNNEL_KEY,
        FunnelState.status == "completed",
        FunnelState.completed_at.is_not(None),
    )
    rows = (
        await session.execute(
            select(MessengerIdentity.channel, func.count(distinct(MessengerIdentity.lead_id)))
            .where(
                MessengerIdentity.lead_id.in_(completed_lead_ids),
                MessengerIdentity.channel.in_(clean_channels),
                MessengerIdentity.is_subscribed.is_(True),
            )
            .group_by(MessengerIdentity.channel)
        )
    ).all()
    by_channel = {channel: 0 for channel in clean_channels}
    for channel, count in rows:
        by_channel[str(channel)] = int(count)
    return FollowupRecipientPreview(total=sum(by_channel.values()), by_channel=by_channel)


async def list_followup_posts(
    session: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
) -> tuple[list[FunnelFollowupPost], int]:
    stmt = (
        select(FunnelFollowupPost)
        .order_by(FunnelFollowupPost.scheduled_at.desc())
        .limit(limit)
        .offset(offset)
    )
    count_stmt = select(func.count()).select_from(FunnelFollowupPost)
    if status:
        stmt = stmt.where(FunnelFollowupPost.status == status)
        count_stmt = count_stmt.where(FunnelFollowupPost.status == status)
    items = list((await session.scalars(stmt)).all())
    total = int(await session.scalar(count_stmt) or 0)
    return items, total


async def get_followup_detail(
    session: AsyncSession,
    post_id: uuid.UUID,
    *,
    limit: int = 100,
    offset: int = 0,
) -> FollowupDetail | None:
    post = await session.get(FunnelFollowupPost, post_id)
    if post is None:
        return None

    rows = (
        await session.execute(
            select(FunnelFollowupDelivery, Lead)
            .join(Lead, Lead.id == FunnelFollowupDelivery.lead_id)
            .where(FunnelFollowupDelivery.followup_post_id == post_id)
            .order_by(FunnelFollowupDelivery.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    deliveries = [
        FollowupDeliveryView(
            id=delivery.id,
            lead_id=delivery.lead_id,
            lead_name=lead.full_name
            or " ".join(part for part in (lead.first_name, lead.last_name) if part)
            or None,
            channel=delivery.channel,
            status=delivery.status,
            external_message_id=delivery.external_message_id,
            attempted_at=delivery.attempted_at,
            sent_at=delivery.sent_at,
            error=delivery.error,
        )
        for delivery, lead in rows
    ]
    return FollowupDetail(post=post, deliveries=deliveries)


async def cancel_followup_post(session: AsyncSession, post_id: uuid.UUID) -> FunnelFollowupPost:
    post = await session.get(FunnelFollowupPost, post_id)
    if post is None:
        raise ValueError("Follow-up post not found.")
    if post.status in {"completed", "sending"}:
        raise ValueError("Completed follow-up post cannot be cancelled.")
    post.status = "cancelled"
    deliveries = (
        await session.scalars(
            select(FunnelFollowupDelivery).where(
                FunnelFollowupDelivery.followup_post_id == post_id
            )
        )
    ).all()
    for delivery in deliveries:
        if delivery.status == "pending":
            delivery.status = "cancelled"
    await session.flush()
    return post


def normalize_followup_channels(channels: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    for channel in channels:
        clean_channel = channel.strip()
        if not clean_channel:
            continue
        if clean_channel not in SUPPORTED_FOLLOWUP_CHANNELS:
            raise ValueError(f"Unsupported follow-up channel: {clean_channel}.")
        if clean_channel not in result:
            result.append(clean_channel)
    if not result:
        raise ValueError("At least one follow-up channel is required.")
    return tuple(result)


def normalize_schedule(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def build_followup_dedupe_key(
    *,
    body: str,
    channels: Sequence[str],
    scheduled_at: datetime,
    source_type: str,
    source_autopost_id: uuid.UUID | None,
) -> str:
    channel_part = ",".join(sorted(channels))
    if source_autopost_id is not None:
        basis = f"source:{source_type}:{source_autopost_id}:{channel_part}"
    else:
        scheduled_minute = scheduled_at.replace(second=0, microsecond=0).isoformat()
        basis = f"manual:{body}:{channel_part}:{scheduled_minute}"
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()
    return f"followup:{digest}"


def strip_followup_marker(body: str, marker: str) -> str:
    pattern = re.compile(re.escape(marker), flags=re.IGNORECASE)
    lines = [pattern.sub("", line).strip() for line in body.splitlines()]
    return "\n".join(line for line in lines if line).strip()
