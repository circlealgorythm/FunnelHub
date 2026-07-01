from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
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
from funnelhub.services.funnel_engine import FUNNEL_LOCAL_TIMEZONE

SUPPORTED_FOLLOWUP_CHANNELS = ("telegram", "vk")
SUPPORTED_FOLLOWUP_DELIVERY_MODES = ("queued", "immediate")
FOLLOWUP_FUNNEL_KEY = "aisu_consultation"
FOLLOWUP_FIRST_DELIVERY_DELAY_DAYS = 1


@dataclass(frozen=True)
class FollowupDeliveryView:
    id: uuid.UUID
    lead_id: uuid.UUID
    lead_name: str | None
    channel: str
    status: str
    available_at: datetime
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
    delivery_mode: str = "queued",
    source_type: str = "manual",
    source_autopost_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> FunnelFollowupPost:
    clean_title = title.strip()
    clean_body = body.strip()
    clean_channels = normalize_followup_channels(channels)
    clean_delivery_mode = normalize_followup_delivery_mode(delivery_mode)
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
        delivery_mode=clean_delivery_mode,
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
        delivery_mode=clean_delivery_mode,
        source_type=clean_source_type,
        source_autopost_id=source_autopost_id,
        dedupe_key=key,
        scheduled_at=send_at,
        metadata_=metadata or {},
    )
    session.add(post)
    await session.flush()

    if clean_delivery_mode == "immediate":
        deliveries = await build_immediate_followup_deliveries(
            session,
            post=post,
            channels=clean_channels,
            available_at=send_at,
        )
    else:
        deliveries = await build_followup_deliveries(session, post=post, channels=clean_channels)
    session.add_all(deliveries)
    post.total_deliveries = len(deliveries)
    if clean_delivery_mode == "immediate" and not deliveries:
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
    if post.delivery_mode != "queued":
        return []

    completed_at_by_lead = await load_completed_followup_leads(session)
    if not completed_at_by_lead:
        return []

    identities = await load_subscribed_followup_identities(
        session,
        lead_ids=list(completed_at_by_lead),
        channels=channels,
    )
    return await build_followup_delivery_queue(
        session,
        posts=[post],
        identities=identities,
        completed_at_by_lead=completed_at_by_lead,
    )


async def build_immediate_followup_deliveries(
    session: AsyncSession,
    *,
    post: FunnelFollowupPost,
    channels: Sequence[str],
    available_at: datetime,
) -> list[FunnelFollowupDelivery]:
    completed_at_by_lead = await load_completed_followup_leads(session)
    if not completed_at_by_lead:
        return []

    identities = await load_subscribed_followup_identities(
        session,
        lead_ids=list(completed_at_by_lead),
        channels=channels,
    )
    existing_keys = await load_existing_delivery_keys(
        session,
        post_ids=[post.id],
        lead_ids=list({identity.lead_id for identity in identities}),
        channels=list({identity.channel for identity in identities}),
    )

    deliveries: list[FunnelFollowupDelivery] = []
    for identity in identities:
        delivery_key = (post.id, identity.lead_id, identity.channel)
        if delivery_key in existing_keys:
            continue
        deliveries.append(
            FunnelFollowupDelivery(
                id=uuid.uuid4(),
                followup_post_id=post.id,
                lead_id=identity.lead_id,
                channel=identity.channel,
                messenger_identity_id=identity.id,
                status="pending",
                available_at=available_at,
                payload={},
            )
        )
    return deliveries


async def enqueue_followup_deliveries_for_completed_lead(
    session: AsyncSession,
    *,
    lead_id: uuid.UUID,
    completed_at: datetime | None = None,
    channels: Sequence[str] = SUPPORTED_FOLLOWUP_CHANNELS,
) -> int:
    clean_channels = normalize_followup_channels(channels)
    completion_time = completed_at or await load_completed_followup_at(session, lead_id)
    if completion_time is None:
        return 0

    posts = list(
        (
            await session.scalars(
                select(FunnelFollowupPost)
                .where(
                    FunnelFollowupPost.status != "cancelled",
                    FunnelFollowupPost.delivery_mode == "queued",
                )
                .order_by(
                    FunnelFollowupPost.scheduled_at.asc(),
                    FunnelFollowupPost.created_at.asc(),
                )
            )
        ).all()
    )
    if not posts:
        return 0

    identities = await load_subscribed_followup_identities(
        session,
        lead_ids=[lead_id],
        channels=clean_channels,
    )
    if not identities:
        return 0

    deliveries = await build_followup_delivery_queue(
        session,
        posts=posts,
        identities=identities,
        completed_at_by_lead={lead_id: completion_time},
    )
    session.add_all(deliveries)
    await session.flush()
    return len(deliveries)


async def load_completed_followup_leads(session: AsyncSession) -> dict[uuid.UUID, datetime]:
    rows = (
        await session.execute(
            select(FunnelState.lead_id, func.min(FunnelState.completed_at))
            .where(
                FunnelState.funnel_key == FOLLOWUP_FUNNEL_KEY,
                FunnelState.status == "completed",
                FunnelState.completed_at.is_not(None),
            )
            .group_by(FunnelState.lead_id)
        )
    ).all()
    return {lead_id: completed_at for lead_id, completed_at in rows if completed_at is not None}


async def load_completed_followup_at(
    session: AsyncSession,
    lead_id: uuid.UUID,
) -> datetime | None:
    return await session.scalar(
        select(func.min(FunnelState.completed_at)).where(
            FunnelState.lead_id == lead_id,
            FunnelState.funnel_key == FOLLOWUP_FUNNEL_KEY,
            FunnelState.status == "completed",
            FunnelState.completed_at.is_not(None),
        )
    )


async def load_subscribed_followup_identities(
    session: AsyncSession,
    *,
    lead_ids: Sequence[uuid.UUID],
    channels: Sequence[str],
) -> list[MessengerIdentity]:
    if not lead_ids:
        return []

    identities = list(
        (
            await session.scalars(
                select(MessengerIdentity)
                .where(
                    MessengerIdentity.lead_id.in_(list(lead_ids)),
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
    return latest_identity_per_lead_channel(identities)


async def build_followup_delivery_queue(
    session: AsyncSession,
    *,
    posts: Sequence[FunnelFollowupPost],
    identities: Sequence[MessengerIdentity],
    completed_at_by_lead: dict[uuid.UUID, datetime],
) -> list[FunnelFollowupDelivery]:
    if not posts or not identities:
        return []

    post_ids = [post.id for post in posts]
    lead_ids = list({identity.lead_id for identity in identities})
    channels = list({identity.channel for identity in identities})
    existing_keys = await load_existing_delivery_keys(
        session,
        post_ids=post_ids,
        lead_ids=lead_ids,
        channels=channels,
    )
    last_available_at = await load_last_delivery_available_at(
        session,
        lead_ids=lead_ids,
        channels=channels,
    )

    deliveries: list[FunnelFollowupDelivery] = []
    for identity in identities:
        completed_at_value = completed_at_by_lead.get(identity.lead_id)
        if completed_at_value is None:
            continue

        lead_channel_key = (identity.lead_id, identity.channel)
        for post in posts:
            if identity.channel not in post.channels:
                continue
            delivery_key = (post.id, identity.lead_id, identity.channel)
            if delivery_key in existing_keys:
                continue

            available_at = calculate_followup_available_at(
                post_scheduled_at=post.scheduled_at,
                completed_at=completed_at_value,
                previous_available_at=last_available_at.get(lead_channel_key),
            )
            last_available_at[lead_channel_key] = available_at
            deliveries.append(
                FunnelFollowupDelivery(
                    id=uuid.uuid4(),
                    followup_post_id=post.id,
                    lead_id=identity.lead_id,
                    channel=identity.channel,
                    messenger_identity_id=identity.id,
                    status="pending",
                    available_at=available_at,
                    payload={},
                )
            )
            post.total_deliveries += 1
            post.completed_at = None
            if post.status in {"completed", "failed"}:
                post.status = "queued" if available_at <= datetime.now(UTC) else "scheduled"
    return deliveries


async def load_existing_delivery_keys(
    session: AsyncSession,
    *,
    post_ids: Sequence[uuid.UUID],
    lead_ids: Sequence[uuid.UUID],
    channels: Sequence[str],
) -> set[tuple[uuid.UUID, uuid.UUID, str]]:
    rows = (
        await session.execute(
            select(
                FunnelFollowupDelivery.followup_post_id,
                FunnelFollowupDelivery.lead_id,
                FunnelFollowupDelivery.channel,
            ).where(
                FunnelFollowupDelivery.followup_post_id.in_(post_ids),
                FunnelFollowupDelivery.lead_id.in_(lead_ids),
                FunnelFollowupDelivery.channel.in_(channels),
            )
        )
    ).all()
    return {(post_id, lead_id, str(channel)) for post_id, lead_id, channel in rows}


async def load_last_delivery_available_at(
    session: AsyncSession,
    *,
    lead_ids: Sequence[uuid.UUID],
    channels: Sequence[str],
) -> dict[tuple[uuid.UUID, str], datetime]:
    rows = (
        await session.execute(
            select(
                FunnelFollowupDelivery.lead_id,
                FunnelFollowupDelivery.channel,
                func.max(FunnelFollowupDelivery.available_at),
            )
            .join(
                FunnelFollowupPost,
                FunnelFollowupPost.id == FunnelFollowupDelivery.followup_post_id,
            )
            .where(
                FunnelFollowupDelivery.lead_id.in_(lead_ids),
                FunnelFollowupDelivery.channel.in_(channels),
                FunnelFollowupDelivery.status != "cancelled",
                FunnelFollowupPost.delivery_mode == "queued",
            )
            .group_by(FunnelFollowupDelivery.lead_id, FunnelFollowupDelivery.channel)
        )
    ).all()
    return {
        (lead_id, str(channel)): available_at
        for lead_id, channel, available_at in rows
        if available_at is not None
    }


def latest_identity_per_lead_channel(
    identities: Sequence[MessengerIdentity],
) -> list[MessengerIdentity]:
    result: list[MessengerIdentity] = []
    seen: set[tuple[uuid.UUID, str]] = set()
    for identity in identities:
        key = (identity.lead_id, identity.channel)
        if key in seen:
            continue
        seen.add(key)
        result.append(identity)
    return result


def calculate_followup_available_at(
    *,
    post_scheduled_at: datetime,
    completed_at: datetime,
    previous_available_at: datetime | None,
) -> datetime:
    completion_local_date = local_date(completed_at)
    candidate = combine_post_time_with_date(
        completion_local_date + timedelta(days=FOLLOWUP_FIRST_DELIVERY_DELAY_DAYS),
        post_scheduled_at,
    )
    if post_scheduled_at > candidate:
        candidate = post_scheduled_at

    if previous_available_at is not None:
        previous_local_date = local_date(previous_available_at)
        while local_date(candidate) <= previous_local_date:
            candidate = combine_post_time_with_date(
                previous_local_date + timedelta(days=1),
                post_scheduled_at,
            )
            if post_scheduled_at > candidate:
                candidate = post_scheduled_at

    return candidate.astimezone(UTC)


def local_date(value: datetime) -> date:
    return normalize_schedule(value).astimezone(FUNNEL_LOCAL_TIMEZONE).date()


def combine_post_time_with_date(target_date: date, post_scheduled_at: datetime) -> datetime:
    post_local_time = normalize_schedule(post_scheduled_at).astimezone(
        FUNNEL_LOCAL_TIMEZONE
    ).time()
    local_value = datetime.combine(
        target_date,
        post_local_time,
        tzinfo=FUNNEL_LOCAL_TIMEZONE,
    )
    return local_value.astimezone(UTC)


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
            .order_by(
                FunnelFollowupDelivery.available_at.asc(),
                FunnelFollowupDelivery.created_at.asc(),
            )
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
            available_at=delivery.available_at,
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


def normalize_followup_delivery_mode(value: str) -> str:
    clean_value = value.strip() or "queued"
    if clean_value not in SUPPORTED_FOLLOWUP_DELIVERY_MODES:
        raise ValueError(f"Unsupported follow-up delivery mode: {clean_value}.")
    return clean_value


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
    delivery_mode: str,
    source_type: str,
    source_autopost_id: uuid.UUID | None,
) -> str:
    channel_part = ",".join(sorted(channels))
    if source_autopost_id is not None:
        basis = f"source:{source_type}:{source_autopost_id}:{channel_part}:{delivery_mode}"
    else:
        scheduled_minute = scheduled_at.replace(second=0, microsecond=0).isoformat()
        basis = f"manual:{body}:{channel_part}:{scheduled_minute}:{delivery_mode}"
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()
    return f"followup:{digest}"


def strip_followup_marker(body: str, marker: str) -> str:
    pattern = re.compile(re.escape(marker), flags=re.IGNORECASE)
    lines = [pattern.sub("", line).strip() for line in body.splitlines()]
    return "\n".join(line for line in lines if line).strip()
