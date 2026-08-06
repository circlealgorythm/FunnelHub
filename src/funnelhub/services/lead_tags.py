from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.models import Event, LeadTag


async def assign_lead_tag(
    session: AsyncSession,
    *,
    lead_id: uuid.UUID,
    tag: str,
    source: str = "most-tsennostey",
) -> bool:
    normalized_tag = " ".join(tag.strip().split())
    if not normalized_tag:
        raise ValueError("Lead tag must not be blank.")

    existing = await session.scalar(
        select(LeadTag).where(LeadTag.lead_id == lead_id, LeadTag.tag == normalized_tag)
    )
    if existing is not None:
        return False

    session.add(
        LeadTag(
            id=uuid.uuid4(),
            lead_id=lead_id,
            tag=normalized_tag,
            source=source,
        )
    )
    session.add(
        Event(
            id=uuid.uuid4(),
            lead_id=lead_id,
            event_type="lead.tag.assigned",
            source=source,
            payload={"tag": normalized_tag},
        )
    )
    await session.flush()
    return True


async def list_lead_tags(session: AsyncSession, lead_id: uuid.UUID) -> list[str]:
    return list(
        await session.scalars(
            select(LeadTag.tag)
            .where(LeadTag.lead_id == lead_id)
            .order_by(LeadTag.created_at.asc(), LeadTag.tag.asc())
        )
    )
