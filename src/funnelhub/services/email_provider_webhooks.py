from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.models import EmailSubscription, Event, Message
from funnelhub.services.getcourse_webhook import normalize_email

PROVIDER_SOURCE = "unisender_go"
UNISENDER_STATUS_EVENT_TYPES = {
    "delivered": "email.delivered",
    "opened": "email.opened",
    "clicked": "email.clicked",
    "soft_bounced": "email.soft_bounced",
    "hard_bounced": "email.hard_bounced",
    "unsubscribed": "email.unsubscribed",
    "subscribed": "email.subscribed",
    "spam": "email.complained",
    "complaint": "email.complained",
    "complained": "email.complained",
}
UNISENDER_STATUS_ALIASES = {
    "delivery": "delivered",
    "ok_delivered": "delivered",
    "read": "opened",
    "open": "opened",
    "ok_read": "opened",
    "link_visited": "clicked",
    "link_clicked": "clicked",
    "click": "clicked",
    "ok_link_visited": "clicked",
    "bounce": "soft_bounced",
    "bounced": "hard_bounced",
    "hard_bounce": "hard_bounced",
    "soft_bounce": "soft_bounced",
    "err_will_retry": "soft_bounced",
    "err_delivered": "hard_bounced",
    "unsubscribe": "unsubscribed",
    "subscribe": "subscribed",
    "spam_block": "spam",
}
SUBSCRIPTION_STOP_STATUSES = {
    "hard_bounced": "bounced",
    "spam": "complained",
    "complaint": "complained",
    "complained": "complained",
    "unsubscribed": "unsubscribed",
}
AUTH_FIELD_RE = re.compile(rb'("auth"\s*:\s*")((?:\\.|[^"\\])*)(")')


@dataclass(frozen=True)
class EmailProviderWebhookResult:
    processed: int
    matched_messages: int
    updated_subscriptions: int
    skipped: int


def load_unisender_go_webhook_payload(raw_body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ValueError("Webhook payload must be valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Webhook payload must be a JSON object.")
    return cast(dict[str, Any], payload)


def verify_unisender_go_webhook_auth(
    *,
    raw_body: bytes,
    payload: dict[str, Any],
    api_key: str,
    received_auth: str,
) -> bool:
    expected_from_raw = calculate_unisender_go_webhook_auth_from_raw(raw_body, api_key)
    if expected_from_raw is not None and hmac.compare_digest(received_auth, expected_from_raw):
        return True

    expected_from_payload = calculate_unisender_go_webhook_auth_from_payload(payload, api_key)
    return hmac.compare_digest(received_auth, expected_from_payload)


def calculate_unisender_go_webhook_auth_from_raw(
    raw_body: bytes,
    api_key: str,
) -> str | None:
    api_key_json = json.dumps(api_key, ensure_ascii=False)[1:-1].encode()
    replaced_body, replacement_count = AUTH_FIELD_RE.subn(
        lambda match: match.group(1) + api_key_json + match.group(3),
        raw_body,
        count=1,
    )
    if replacement_count != 1:
        return None
    return hashlib.md5(replaced_body).hexdigest()


def calculate_unisender_go_webhook_auth_from_payload(
    payload: dict[str, Any],
    api_key: str,
) -> str:
    payload_for_hash = {**payload, "auth": api_key}
    canonical_body = json.dumps(
        payload_for_hash,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return hashlib.md5(canonical_body).hexdigest()


async def process_unisender_go_webhook(
    session: AsyncSession,
    payload: dict[str, Any],
) -> EmailProviderWebhookResult:
    events_by_user = payload.get("events_by_user")
    if not isinstance(events_by_user, list):
        raise ValueError("Webhook payload must contain events_by_user list.")

    processed = 0
    matched_messages = 0
    updated_subscriptions = 0
    skipped = 0

    for user_events in events_by_user:
        if not isinstance(user_events, dict):
            skipped += 1
            continue

        fallback_job_id = normalize_optional_string(user_events.get("job_id"))
        fallback_email = normalize_optional_string(user_events.get("email"))
        fallback_metadata = user_events.get("metadata")
        fallback_provider_metadata = (
            fallback_metadata if isinstance(fallback_metadata, dict) else {}
        )
        raw_events = user_events.get("events")
        if raw_events is None:
            raw_events = user_events.get("Events")
        if not isinstance(raw_events, list):
            skipped += 1
            continue

        for raw_event in raw_events:
            if not isinstance(raw_event, dict):
                skipped += 1
                continue

            event_data = raw_event.get("event_data")
            event_data_dict = event_data if isinstance(event_data, dict) else {}
            provider_status = normalize_provider_status(
                event_data_dict=event_data_dict,
                event_name=raw_event.get("event_name") or raw_event.get("EventName"),
            )
            if provider_status is None:
                skipped += 1
                continue

            event_type = UNISENDER_STATUS_EVENT_TYPES.get(provider_status)
            if event_type is None:
                skipped += 1
                continue

            job_id = normalize_optional_string(event_data_dict.get("job_id")) or fallback_job_id
            email = normalize_optional_string(event_data_dict.get("email")) or fallback_email
            metadata = event_data_dict.get("metadata")
            provider_metadata = (
                metadata if isinstance(metadata, dict) else fallback_provider_metadata
            )
            occurred_at = parse_unisender_event_time(
                event_data_dict.get("event_time") or raw_event.get("event_time")
            )
            message = await find_email_message(
                session=session,
                job_id=job_id,
                metadata=provider_metadata,
            )
            subscription = await find_email_subscription(
                session=session,
                email=email,
                lead_id=message.lead_id if message is not None else parse_uuid(
                    provider_metadata.get("lead_id")
                ),
            )
            lead_id = message.lead_id if message is not None else (
                subscription.lead_id if subscription is not None else None
            )
            dedupe_key = build_unisender_event_dedupe_key(
                job_id=job_id,
                email=email,
                provider_status=provider_status,
                occurred_at=occurred_at,
                event_data=event_data_dict,
                message_id=message.id if message is not None else parse_uuid(
                    provider_metadata.get("message_id")
                ),
            )
            if await event_exists(session, dedupe_key):
                skipped += 1
                continue

            if message is not None:
                apply_email_message_provider_event(
                    message=message,
                    provider_status=provider_status,
                    occurred_at=occurred_at,
                    job_id=job_id,
                    event_data=event_data_dict,
                )
                matched_messages += 1

            if subscription is not None and apply_subscription_provider_event(
                subscription=subscription,
                provider_status=provider_status,
                occurred_at=occurred_at,
            ):
                updated_subscriptions += 1

            session.add(
                Event(
                    id=uuid.uuid4(),
                    lead_id=lead_id,
                    event_type=event_type,
                    source=PROVIDER_SOURCE,
                    occurred_at=occurred_at,
                    payload={
                        "provider": PROVIDER_SOURCE,
                        "job_id": job_id,
                        "email": email,
                        "provider_status": provider_status,
                        "event_name": raw_event.get("event_name"),
                        "message_id": str(message.id) if message is not None else None,
                        "email_subscription_id": (
                            str(subscription.id) if subscription is not None else None
                        ),
                        "event_data": event_data_dict,
                        "metadata": {
                            key: value
                            for key, value in provider_metadata.items()
                            if key in {"lead_id", "message_id", "funnel_key", "step_key"}
                        },
                    },
                    dedupe_key=dedupe_key,
                )
            )
            processed += 1

    await session.flush()
    return EmailProviderWebhookResult(
        processed=processed,
        matched_messages=matched_messages,
        updated_subscriptions=updated_subscriptions,
        skipped=skipped,
    )


async def find_email_message(
    *,
    session: AsyncSession,
    job_id: str | None,
    metadata: dict[str, Any],
) -> Message | None:
    message_id = parse_uuid(metadata.get("message_id"))
    if message_id is not None:
        message = cast(
            Message | None,
            await session.scalar(
                select(Message).where(
                    Message.id == message_id,
                    Message.channel == "email",
                    Message.direction == "outbound",
                )
            )
        )
        if message is not None:
            return message

    if job_id:
        message = cast(
            Message | None,
            await session.scalar(
                select(Message)
                .where(
                    Message.external_message_id == job_id,
                    Message.channel == "email",
                    Message.direction == "outbound",
                )
                .order_by(desc(Message.created_at))
                .limit(1)
            )
        )
        if message is not None:
            return message

    lead_id = parse_uuid(metadata.get("lead_id"))
    if lead_id is None:
        return None

    return cast(
        Message | None,
        await session.scalar(
            select(Message)
            .where(
                Message.lead_id == lead_id,
                Message.channel == "email",
                Message.direction == "outbound",
            )
            .order_by(desc(Message.created_at))
            .limit(1)
        ),
    )


async def find_email_subscription(
    *,
    session: AsyncSession,
    email: str | None,
    lead_id: uuid.UUID | None,
) -> EmailSubscription | None:
    if lead_id is not None:
        subscription = await session.scalar(
            select(EmailSubscription)
            .where(EmailSubscription.lead_id == lead_id)
            .order_by(desc(EmailSubscription.created_at))
            .limit(1)
        )
        if subscription is not None:
            return subscription

    normalized_email = normalize_email(email)
    if normalized_email is None:
        return None
    return cast(
        EmailSubscription | None,
        await session.scalar(
            select(EmailSubscription).where(EmailSubscription.normalized_email == normalized_email)
        ),
    )


def apply_email_message_provider_event(
    *,
    message: Message,
    provider_status: str,
    occurred_at: datetime,
    job_id: str | None,
    event_data: dict[str, Any],
) -> None:
    message_status = map_provider_status_to_message_status(provider_status)
    if message_status is not None:
        message.status = message_status
    if provider_status == "delivered":
        message.delivered_at = message.delivered_at or occurred_at
    if provider_status in {"opened", "clicked"}:
        message.read_at = message.read_at or occurred_at
    if provider_status == "clicked" and message.read_at is None:
        message.read_at = occurred_at

    metadata = dict(message.metadata_ or {})
    event_summary = {
        "provider": PROVIDER_SOURCE,
        "status": provider_status,
        "event_time": occurred_at.isoformat(),
        "job_id": job_id,
    }
    if isinstance(event_data.get("url"), str):
        event_summary["url"] = event_data["url"]
        metadata["last_clicked_url"] = event_data["url"]
    if provider_status == "opened":
        metadata["open_count"] = int(metadata.get("open_count") or 0) + 1
    if provider_status == "clicked":
        metadata["click_count"] = int(metadata.get("click_count") or 0) + 1

    provider_events = metadata.get("provider_events")
    provider_event_list = list(provider_events) if isinstance(provider_events, list) else []
    provider_event_list.append(event_summary)
    metadata["provider_events"] = provider_event_list[-50:]
    metadata["last_provider_event"] = event_summary
    message.metadata_ = metadata


def map_provider_status_to_message_status(provider_status: str) -> str | None:
    if provider_status == "delivered":
        return "delivered"
    if provider_status in {"opened", "clicked"}:
        return "read"
    if provider_status in {
        "soft_bounced",
        "hard_bounced",
        "spam",
        "complaint",
        "complained",
        "unsubscribed",
    }:
        return "failed"
    return None


def apply_subscription_provider_event(
    *,
    subscription: EmailSubscription,
    provider_status: str,
    occurred_at: datetime,
) -> bool:
    new_status = SUBSCRIPTION_STOP_STATUSES.get(provider_status)
    if new_status is None:
        return False
    if subscription.status == new_status and subscription.unsubscribed_at is not None:
        return False

    subscription.status = new_status
    subscription.unsubscribed_at = subscription.unsubscribed_at or occurred_at
    return True


async def event_exists(session: AsyncSession, dedupe_key: str) -> bool:
    existing = await session.scalar(select(Event.id).where(Event.dedupe_key == dedupe_key))
    return existing is not None


def build_unisender_event_dedupe_key(
    *,
    job_id: str | None,
    email: str | None,
    provider_status: str,
    occurred_at: datetime,
    event_data: dict[str, Any],
    message_id: uuid.UUID | None,
) -> str:
    raw_key = json.dumps(
        {
            "provider": PROVIDER_SOURCE,
            "job_id": job_id,
            "email": normalize_email(email),
            "message_id": str(message_id) if message_id is not None else None,
            "status": provider_status,
            "event_time": occurred_at.isoformat(),
            "url": event_data.get("url"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(raw_key.encode()).hexdigest()
    return f"email.{PROVIDER_SOURCE}:{digest}"


def normalize_provider_status(
    *,
    event_data_dict: dict[str, Any],
    event_name: Any,
) -> str | None:
    status = first_string(
        event_data_dict.get("status"),
        event_data_dict.get("email_status"),
        event_data_dict.get("Status"),
        event_name,
    )
    if status is None:
        return None
    normalized = status.strip().lower().replace("-", "_")
    normalized = UNISENDER_STATUS_ALIASES.get(normalized, normalized)
    if normalized == "transactional_email_status":
        return None
    return normalized or None


def first_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value
    return None


def parse_unisender_event_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        raw_value = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(raw_value)
        except ValueError:
            parsed = datetime.strptime(raw_value, "%Y-%m-%d %H:%M:%S")
    else:
        parsed = datetime.now(UTC)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_uuid(value: Any) -> uuid.UUID | None:
    if not isinstance(value, str):
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def normalize_optional_string(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, int):
        return str(value)
    return None
