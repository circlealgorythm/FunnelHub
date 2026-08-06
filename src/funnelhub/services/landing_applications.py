from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.models import Event, Lead, Message
from funnelhub.services.bot_linking import create_or_get_active_bot_link_token
from funnelhub.services.getcourse_webhook import (
    find_existing_lead,
    normalize_email,
    normalize_phone,
    upsert_contact,
    upsert_email_subscription,
)
from funnelhub.services.inbox import get_or_create_conversation
from funnelhub.services.lead_tags import assign_lead_tag

MOST_TSENNOSTEY_SOURCE = "most-tsennostey"
MOST_TSENNOSTEY_APPLICATION_TEXT = "Новая заявка с сайта «Мост ценностей»."


@dataclass(frozen=True)
class LandingApplicationResult:
    lead_id: uuid.UUID
    conversation_id: uuid.UUID
    bot_link_token: str
    created: bool


async def ingest_most_tsennostey_application(
    session: AsyncSession,
    *,
    name: str,
    phone: str,
    email: str,
) -> LandingApplicationResult:
    normalized_email = normalize_email(email)
    normalized_phone = normalize_phone(phone)
    if normalized_email is None or normalized_phone is None:
        raise ValueError("Application must include email and phone.")

    lead = await find_existing_lead(
        session=session,
        getcourse_user_id=None,
        normalized_email=normalized_email,
        normalized_phone=normalized_phone,
    )
    created = lead is None
    now = datetime.now(UTC)
    if lead is None:
        lead = Lead(id=uuid.uuid4(), raw_getcourse_data={})
        session.add(lead)

    lead.full_name = name
    lead.source = MOST_TSENNOSTEY_SOURCE
    lead.updated_at = now
    lead.raw_getcourse_data = {
        **(lead.raw_getcourse_data or {}),
        "source": MOST_TSENNOSTEY_SOURCE,
        "latest_application": {
            "name": name,
            "phone": phone,
            "email": email,
            "received_at": now.isoformat(),
        },
    }
    await session.flush()

    await upsert_contact(
        session=session,
        lead=lead,
        contact_type="email",
        value=email,
        normalized_value=normalized_email,
    )
    await upsert_contact(
        session=session,
        lead=lead,
        contact_type="phone",
        value=phone,
        normalized_value=normalized_phone,
    )
    await upsert_email_subscription(
        session=session,
        lead=lead,
        normalized={"email": email, "normalized_email": normalized_email},
    )
    bot_link_token = await create_or_get_active_bot_link_token(session, lead)
    await assign_lead_tag(session, lead_id=lead.id, tag="заявка с сайта")

    conversation = await get_or_create_conversation(
        session=session,
        lead_id=lead.id,
        channel="email",
    )
    conversation.status = "needs_reply"
    conversation.last_message_at = now
    session.add(
        Message(
            id=uuid.uuid4(),
            lead_id=lead.id,
            conversation_id=conversation.id,
            channel="email",
            direction="inbound",
            message_type="application",
            body=MOST_TSENNOSTEY_APPLICATION_TEXT,
            status="received",
            sent_at=now,
            metadata_={"source": MOST_TSENNOSTEY_SOURCE},
        )
    )
    session.add(
        Event(
            id=uuid.uuid4(),
            lead_id=lead.id,
            event_type="landing.application.received",
            source=MOST_TSENNOSTEY_SOURCE,
            payload={"name": name, "phone": phone, "email": email},
        )
    )
    await session.flush()
    return LandingApplicationResult(
        lead_id=lead.id,
        conversation_id=conversation.id,
        bot_link_token=bot_link_token.token,
        created=created,
    )
