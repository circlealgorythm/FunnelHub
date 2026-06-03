from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.config import Settings
from funnelhub.db.models import EmailSubscription, Event, Message


class EmailProviderClient(Protocol):
    async def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        text: str,
        html: str | None = None,
        from_email: str | None = None,
        from_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EmailProviderSendResult: ...


@dataclass(frozen=True)
class EmailProviderSendResult:
    external_message_id: str | None = None
    raw_response: dict[str, Any] | None = None


class DebugEmailProviderClient:
    async def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        text: str,
        html: str | None = None,
        from_email: str | None = None,
        from_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EmailProviderSendResult:
        return EmailProviderSendResult(
            external_message_id=f"debug-{secrets.token_hex(8)}",
            raw_response={
                "provider": "debug",
                "to_email": to_email,
                "subject": subject,
            },
        )


@dataclass(frozen=True)
class EmailSendResult:
    message_id: uuid.UUID
    external_message_id: str | None


def build_email_provider_client(settings: Settings) -> EmailProviderClient | None:
    if settings.email_provider == "debug":
        return DebugEmailProviderClient()
    if settings.email_provider == "disabled":
        return None
    raise ValueError(f"Unsupported EMAIL_PROVIDER: {settings.email_provider}")


async def send_email_text_message(
    *,
    session: AsyncSession,
    client: EmailProviderClient,
    lead_id: uuid.UUID,
    subject: str,
    text: str,
    public_base_url: str,
    from_email: str | None = None,
    from_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> EmailSendResult:
    subscription = await get_subscribed_email_subscription(session, lead_id)
    if subscription is None:
        raise ValueError("Lead has no subscribed email subscription.")

    await ensure_email_unsubscribe_token(session, subscription)
    unsubscribe_url = build_unsubscribe_url(public_base_url, subscription.unsubscribe_token)
    body = append_unsubscribe_footer(text, unsubscribe_url)
    message_metadata = {
        **(metadata or {}),
        "subject": subject,
        "to_email": subscription.email,
        "unsubscribe_url": unsubscribe_url,
    }
    now = datetime.now(UTC)
    message = Message(
        id=uuid.uuid4(),
        lead_id=lead_id,
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
        sent_message = await client.send_email(
            to_email=subscription.email,
            subject=subject,
            text=body,
            html=None,
            from_email=from_email,
            from_name=from_name,
            metadata={
                "lead_id": str(lead_id),
                "message_id": str(message.id),
                **(metadata or {}),
            },
        )
    except Exception as exc:
        message.status = "failed"
        message.metadata_ = {**message_metadata, "error": str(exc)}
        await session.flush()
        raise

    message.external_message_id = sent_message.external_message_id
    message.status = "sent"
    message.sent_at = now
    if sent_message.raw_response:
        message.metadata_ = {
            **message_metadata,
            "provider_response": sent_message.raw_response,
        }
    await session.flush()
    return EmailSendResult(
        message_id=message.id,
        external_message_id=sent_message.external_message_id,
    )


async def get_subscribed_email_subscription(
    session: AsyncSession,
    lead_id: uuid.UUID,
) -> EmailSubscription | None:
    return cast(
        EmailSubscription | None,
        await session.scalar(
            select(EmailSubscription)
            .where(
                EmailSubscription.lead_id == lead_id,
                EmailSubscription.status == "subscribed",
                EmailSubscription.unsubscribed_at.is_(None),
            )
            .order_by(EmailSubscription.created_at.desc())
        )
    )


async def ensure_email_unsubscribe_token(
    session: AsyncSession,
    subscription: EmailSubscription,
) -> str:
    if subscription.unsubscribe_token:
        return subscription.unsubscribe_token

    subscription.unsubscribe_token = await generate_unique_unsubscribe_token(session)
    await session.flush()
    return subscription.unsubscribe_token


async def generate_unique_unsubscribe_token(session: AsyncSession) -> str:
    for _ in range(5):
        token = secrets.token_urlsafe(32)
        existing = await session.scalar(
            select(EmailSubscription.id).where(EmailSubscription.unsubscribe_token == token)
        )
        if existing is None:
            return token
    raise RuntimeError("Could not generate a unique email unsubscribe token.")


async def unsubscribe_email_by_token(
    session: AsyncSession,
    token: str,
) -> EmailSubscription | None:
    subscription = await session.scalar(
        select(EmailSubscription).where(EmailSubscription.unsubscribe_token == token)
    )
    if subscription is None:
        return None

    was_subscribed = subscription.status != "unsubscribed"
    now = datetime.now(UTC)
    subscription.status = "unsubscribed"
    subscription.unsubscribed_at = subscription.unsubscribed_at or now
    if was_subscribed:
        session.add(
            Event(
                id=uuid.uuid4(),
                lead_id=subscription.lead_id,
                event_type="email.unsubscribed",
                source="email",
                occurred_at=now,
                payload={
                    "email_subscription_id": str(subscription.id),
                    "email": subscription.email,
                },
                dedupe_key=f"email.unsubscribed:{subscription.id}",
            )
        )
    await session.flush()
    return subscription


def build_unsubscribe_url(public_base_url: str, token: str | None) -> str:
    if not token:
        raise ValueError("Email unsubscribe token is missing.")
    return f"{public_base_url.rstrip('/')}/email/unsubscribe/{quote(token, safe='')}"


def append_unsubscribe_footer(text: str, unsubscribe_url: str) -> str:
    return (
        f"{text.rstrip()}\n\n"
        "---\n"
        "Если вы больше не хотите получать письма, можно отписаться здесь:\n"
        f"{unsubscribe_url}"
    )
