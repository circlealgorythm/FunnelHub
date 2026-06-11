from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.models import Broadcast, BroadcastTarget, Lead
from funnelhub.services.inbox_database import (
    build_lead_search_filter,
    lead_contact_subquery,
    messenger_identity_subquery,
)


@dataclass(frozen=True)
class BroadcastTargetView:
    id: uuid.UUID
    lead_id: uuid.UUID
    lead_name: str | None
    lead_contact: str | None
    status: str
    error: str | None


async def create_broadcast(
    session: AsyncSession,
    segment_query: str | None,
    channels: list[str],
    message_text: str,
) -> Broadcast:
    clean_segment_query = segment_query.strip() if segment_query else None
    clean_message_text = message_text.strip()
    broadcast = Broadcast(
        id=uuid.uuid4(),
        segment_query=clean_segment_query or None,
        channels=channels,
        message_text=clean_message_text,
        status="created",
        total_leads=0,
    )
    session.add(broadcast)

    lead_stmt = select(Lead.id)
    if broadcast.segment_query:
        lead_stmt = lead_stmt.where(build_lead_search_filter(broadcast.segment_query))

    lead_ids = (await session.scalars(lead_stmt)).all()
    
    broadcast.total_leads = len(lead_ids)
    if not lead_ids:
        broadcast.status = "completed"

    targets = [
        BroadcastTarget(
            id=uuid.uuid4(),
            broadcast_id=broadcast.id,
            lead_id=lead_id,
            status="pending",
        )
        for lead_id in lead_ids
    ]
    session.add_all(targets)
    
    await session.commit()
    await session.refresh(broadcast)
    return broadcast


async def list_broadcasts(
    session: AsyncSession,
    limit: int = 50,
    offset: int = 0,
) -> tuple[Sequence[Broadcast], int]:
    stmt = select(Broadcast).order_by(Broadcast.created_at.desc()).limit(limit).offset(offset)
    broadcasts = (await session.scalars(stmt)).all()
    
    count_stmt = select(func.count()).select_from(Broadcast)
    total = int(await session.scalar(count_stmt) or 0)
    
    return broadcasts, total


async def get_broadcast_detail(
    session: AsyncSession,
    broadcast_id: uuid.UUID,
) -> Broadcast | None:
    return await session.get(Broadcast, broadcast_id)


async def list_broadcast_targets(
    session: AsyncSession,
    broadcast_id: uuid.UUID,
    *,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[BroadcastTargetView], int] | None:
    if await session.get(Broadcast, broadcast_id) is None:
        return None

    email = lead_contact_subquery("email")
    phone = lead_contact_subquery("phone")
    telegram = messenger_identity_subquery("telegram")
    vk = messenger_identity_subquery("vk")

    count_stmt = (
        select(func.count())
        .select_from(BroadcastTarget)
        .where(BroadcastTarget.broadcast_id == broadcast_id)
    )
    total = int(await session.scalar(count_stmt) or 0)

    stmt = (
        select(
            BroadcastTarget,
            Lead,
            email.label("email"),
            phone.label("phone"),
            telegram.label("telegram"),
            vk.label("vk"),
        )
        .join(Lead, Lead.id == BroadcastTarget.lead_id)
        .where(BroadcastTarget.broadcast_id == broadcast_id)
        .order_by(BroadcastTarget.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()

    items: list[BroadcastTargetView] = []
    for target, lead, email_value, phone_value, telegram_value, vk_value in rows:
        lead_name = lead.full_name or " ".join(
            part for part in (lead.first_name, lead.last_name) if part
        ) or None
        items.append(
            BroadcastTargetView(
                id=target.id,
                lead_id=target.lead_id,
                lead_name=lead_name,
                lead_contact=email_value or phone_value or telegram_value or vk_value,
                status=target.status,
                error=target.error,
            )
        )

    return items, total
