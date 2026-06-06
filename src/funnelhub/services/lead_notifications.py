from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.config import Settings
from funnelhub.db.models import Event, Lead, LeadContact, Message
from funnelhub.services.email_messaging import EmailProviderClient, build_email_provider_client

logger = logging.getLogger(__name__)
SENT_EVENT_TYPE = "lead.application.notification.sent"
FAILED_EVENT_TYPE = "lead.application.notification.failed"


async def send_lead_application_notification(
    *,
    session: AsyncSession,
    settings: Settings,
    lead_id: uuid.UUID,
    created: bool,
    source: str,
    client: EmailProviderClient | None = None,
) -> int:
    recipients = parse_notification_recipients(settings.lead_notification_email_to)
    if not recipients:
        return 0
    if await has_recent_notification(session, lead_id, settings):
        return 0

    try:
        email_client = client or build_email_provider_client(settings)
    except Exception as exc:
        await record_notification_event(
            session=session,
            lead_id=lead_id,
            event_type=FAILED_EVENT_TYPE,
            source=source,
            payload={"error": str(exc), "stage": "build_email_client"},
        )
        logger.exception("Lead application notification email client is not available")
        return 0

    if email_client is None:
        return 0

    lead = await session.get(Lead, lead_id)
    if lead is None:
        return 0

    contacts = await load_lead_contacts(session, lead_id)
    subject = "Новая заявка на консультацию" if created else "Повторная заявка на консультацию"
    body = build_lead_notification_text(
        lead=lead,
        contacts=contacts,
        created=created,
        source=source,
        settings=settings,
    )
    html = build_lead_notification_html(body)
    sent = 0
    for recipient in recipients:
        if await send_one_notification(
            session=session,
            client=email_client,
            lead=lead,
            recipient=recipient,
            subject=subject,
            body=body,
            html=html,
            settings=settings,
            source=source,
        ):
            sent += 1
    return sent


def parse_notification_recipients(value: str | None) -> list[str]:
    if value is None:
        return []
    recipients: list[str] = []
    for chunk in value.replace(";", ",").split(","):
        email = chunk.strip()
        if email and email not in recipients:
            recipients.append(email)
    return recipients


async def has_recent_notification(
    session: AsyncSession,
    lead_id: uuid.UUID,
    settings: Settings,
) -> bool:
    cooldown = max(settings.lead_notification_cooldown_seconds, 0)
    if cooldown == 0:
        return False

    cutoff = datetime.now(UTC) - timedelta(seconds=cooldown)
    existing = await session.scalar(
        select(Event.id)
        .where(
            Event.lead_id == lead_id,
            Event.event_type.in_([SENT_EVENT_TYPE, FAILED_EVENT_TYPE]),
            Event.occurred_at >= cutoff,
        )
        .order_by(Event.occurred_at.desc())
    )
    return existing is not None


async def load_lead_contacts(session: AsyncSession, lead_id: uuid.UUID) -> dict[str, str]:
    contacts = (
        await session.scalars(
            select(LeadContact)
            .where(LeadContact.lead_id == lead_id)
            .order_by(LeadContact.is_primary.desc(), LeadContact.created_at.desc())
        )
    ).all()
    result: dict[str, str] = {}
    for contact in contacts:
        result.setdefault(contact.contact_type, contact.value)
    return result


async def send_one_notification(
    *,
    session: AsyncSession,
    client: EmailProviderClient,
    lead: Lead,
    recipient: str,
    subject: str,
    body: str,
    html: str,
    settings: Settings,
    source: str,
) -> bool:
    now = datetime.now(UTC)
    message_metadata: dict[str, Any] = {
        "notification_type": "lead_application",
        "to_email": recipient,
        "subject": subject,
        "source": source,
    }
    message = Message(
        id=uuid.uuid4(),
        lead_id=lead.id,
        channel="email",
        direction="outbound",
        message_type="text",
        body=body,
        status="created",
        metadata_=message_metadata,
    )
    session.add(message)
    await session.flush()

    try:
        result = await client.send_email(
            to_email=recipient,
            subject=subject,
            text=body,
            html=html,
            from_email=settings.email_from_email,
            from_name=settings.email_from_name,
            metadata={
                "lead_id": str(lead.id),
                "message_id": str(message.id),
                "notification_type": "lead_application",
                "source": source,
            },
        )
    except Exception as exc:
        message.status = "failed"
        message.metadata_ = {**message_metadata, "error": str(exc)}
        await record_notification_event(
            session=session,
            lead_id=lead.id,
            event_type=FAILED_EVENT_TYPE,
            source=source,
            payload={
                "message_id": str(message.id),
                "to_email": recipient,
                "error": str(exc),
            },
        )
        await session.flush()
        logger.exception("Failed to send lead application notification")
        return False

    message.external_message_id = result.external_message_id
    message.status = "sent"
    message.sent_at = now
    if result.raw_response is not None:
        message.metadata_ = {**message_metadata, "provider_response": result.raw_response}
    await record_notification_event(
        session=session,
        lead_id=lead.id,
        event_type=SENT_EVENT_TYPE,
        source=source,
        payload={
            "message_id": str(message.id),
            "to_email": recipient,
        },
    )
    await session.flush()
    return True


async def record_notification_event(
    *,
    session: AsyncSession,
    lead_id: uuid.UUID,
    event_type: str,
    source: str,
    payload: dict[str, Any],
) -> None:
    session.add(
        Event(
            id=uuid.uuid4(),
            lead_id=lead_id,
            event_type=event_type,
            source="funnelhub",
            occurred_at=datetime.now(UTC),
            payload={**payload, "application_source": source},
        )
    )


def build_lead_notification_text(
    *,
    lead: Lead,
    contacts: dict[str, str],
    created: bool,
    source: str,
    settings: Settings,
) -> str:
    raw = lead.raw_getcourse_data or {}
    vk_id = raw.get("vk_id") or raw.get("VK-ID") or raw.get("vk_user_id")
    lines = [
        "В FunnelHub поступила заявка.",
        "",
        f"Тип: {'новый лид' if created else 'повторная заявка'}",
        f"Источник заявки: {source}",
        f"Имя: {lead.full_name or lead.first_name or raw.get('name') or '-'}",
        f"Телефон: {contacts.get('phone') or raw.get('phone') or '-'}",
        f"Email: {contacts.get('email') or raw.get('email') or '-'}",
        f"Форма: {raw.get('form_type') or '-'}",
        f"Источник/UTM: {raw.get('source') or raw.get('utm_source') or '-'}",
        f"ID GetCourse: {lead.getcourse_user_id or raw.get('gc_user_id') or '-'}",
        f"VK-ID: {vk_id or '-'}",
        f"Lead ID: {lead.id}",
    ]
    if settings.inbox_app_url:
        lines.append(f"Inbox: {settings.inbox_app_url.rstrip('/')}")
    return "\n".join(str(line) for line in lines)


def build_lead_notification_html(text: str) -> str:
    return (
        "<!doctype html><html><body>"
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;">'
        + "<br>".join(escape(line) for line in text.splitlines())
        + "</div></body></html>"
    )
