from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.config import Settings
from funnelhub.db.models import FunnelState
from funnelhub.services.funnel_engine import load_funnel_definition, start_funnel_for_lead


async def start_default_funnel_for_lead(
    session: AsyncSession,
    settings: Settings,
    lead_id: uuid.UUID,
    now: datetime | None = None,
) -> FunnelState:
    definition = load_funnel_definition(settings.default_funnel_path)
    return await start_funnel_for_lead(
        session=session,
        lead_id=lead_id,
        definition=definition,
        now=now,
    )
