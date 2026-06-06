from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.config import Settings
from funnelhub.db.models import FunnelState
from funnelhub.services.email_messaging import get_subscribed_email_subscription
from funnelhub.services.funnel_engine import (
    build_state_metadata,
    load_funnel_definition,
    normalize_datetime,
    start_funnel_for_lead,
)


async def start_default_funnel_for_lead(
    session: AsyncSession,
    settings: Settings,
    lead_id: uuid.UUID,
    now: datetime | None = None,
    messenger_channel: str | None = None,
) -> FunnelState:
    definition = load_funnel_definition(settings.default_funnel_path)
    state = await start_funnel_for_lead(
        session=session,
        lead_id=lead_id,
        definition=definition,
        channel=messenger_channel or "unknown",
        now=now,
    )
    if messenger_channel is not None:
        state.metadata_ = {
            **(state.metadata_ or {}),
            "messenger_channel": messenger_channel,
        }
        await session.flush()
    return state


async def start_default_email_funnel_for_lead(
    session: AsyncSession,
    settings: Settings,
    lead_id: uuid.UUID,
    now: datetime | None = None,
) -> FunnelState | None:
    if not settings.default_email_funnel_path:
        return None

    subscription = await get_subscribed_email_subscription(session, lead_id)
    if subscription is None:
        return None

    definition = load_funnel_definition(settings.default_email_funnel_path)
    return await start_funnel_for_lead(
        session=session,
        lead_id=lead_id,
        definition=definition,
        channel="email",
        now=now,
    )


async def restart_default_funnel_for_lead(
    session: AsyncSession,
    settings: Settings,
    lead_id: uuid.UUID,
    now: datetime | None = None,
    messenger_channel: str | None = None,
) -> FunnelState:
    current_time = normalize_datetime(now)
    definition = load_funnel_definition(settings.default_funnel_path)
    state = await start_funnel_for_lead(
        session=session,
        lead_id=lead_id,
        definition=definition,
        channel=messenger_channel or "unknown",
        now=current_time,
    )
    first_step = definition.steps[0]
    metadata = build_state_metadata(definition=definition, step_index=0)
    if messenger_channel is not None:
        metadata["messenger_channel"] = messenger_channel
    metadata["restarted_at"] = current_time.isoformat()
    metadata["restart_reason"] = "bot_start"
    state.status = "active"
    state.current_step_key = first_step.key
    state.next_run_at = current_time
    state.completed_at = None
    state.paused_at = None
    state.metadata_ = metadata
    await session.flush()
    return state
