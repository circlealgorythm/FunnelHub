from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.models import Broadcast, BroadcastTarget, Lead
from funnelhub.services.inbox_database import build_lead_search_filter


async def create_broadcast(
    session: AsyncSession,
    segment_query: str | None,
    channels: list[str],
    message_text: str,
) -> Broadcast:
    broadcast = Broadcast(
        id=uuid.uuid4(),
        segment_query=segment_query.strip() if segment_query else None,
        channels=channels,
        message_text=message_text,
        status="created",
        total_leads=0,
    )
    session.add(broadcast)

    lead_stmt = select(Lead.id)
    if broadcast.segment_query:
        lead_stmt = lead_stmt.where(build_lead_search_filter(broadcast.segment_query))

    lead_ids = (await session.scalars(lead_stmt)).all()
    
    broadcast.total_leads = len(lead_ids)

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
    
    from sqlalchemy import func
    count_stmt = select(func.count()).select_from(Broadcast)
    total = int(await session.scalar(count_stmt) or 0)
    
    return broadcasts, total


async def get_broadcast_detail(
    session: AsyncSession,
    broadcast_id: uuid.UUID,
) -> Broadcast | None:
    return await session.get(Broadcast, broadcast_id)
