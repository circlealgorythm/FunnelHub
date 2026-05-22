from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.models import (
    EmailSubscription,
    Event,
    Lead,
    LeadContact,
    LeadCustomField,
    LeadExternalId,
    LeadUtm,
)

EMPTY_VALUES = {"", "(empty)", "none", "null"}
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_group")


@dataclass(frozen=True)
class GetCourseWebhookIngestionResult:
    lead_id: uuid.UUID
    created: bool


async def ingest_getcourse_webhook(
    session: AsyncSession,
    payload: dict[str, Any],
) -> GetCourseWebhookIngestionResult:
    normalized = normalize_getcourse_payload(payload)
    if (
        normalized["getcourse_user_id"] is None
        and normalized["normalized_email"] is None
        and normalized["normalized_phone"] is None
    ):
        raise ValueError("Webhook must include gc_user_id, email, or phone.")

    lead = await find_existing_lead(
        session=session,
        getcourse_user_id=normalized["getcourse_user_id"],
        normalized_email=normalized["normalized_email"],
        normalized_phone=normalized["normalized_phone"],
    )
    created = lead is None
    if lead is None:
        lead = Lead(id=uuid.uuid4())
        session.add(lead)

    apply_payload_to_lead(lead, normalized)
    await session.flush()

    await upsert_getcourse_external_id(session, lead, normalized)
    await upsert_contact(
        session=session,
        lead=lead,
        contact_type="email",
        value=normalized["email"],
        normalized_value=normalized["normalized_email"],
    )
    await upsert_contact(
        session=session,
        lead=lead,
        contact_type="phone",
        value=normalized["phone"],
        normalized_value=normalized["normalized_phone"],
    )
    await upsert_email_subscription(session, lead, normalized)
    await upsert_custom_fields(session, lead, normalized)

    if has_utm_data(normalized):
        session.add(
            LeadUtm(
                id=uuid.uuid4(),
                lead_id=lead.id,
                source_kind="getcourse_system",
                utm_source=normalized["utm_source"],
                utm_medium=normalized["utm_medium"],
                utm_campaign=normalized["utm_campaign"],
                utm_term=normalized["utm_term"],
                utm_content=normalized["utm_content"],
                utm_group=normalized["utm_group"],
                raw_data=normalized["raw_payload"],
            )
        )

    session.add(
        Event(
            id=uuid.uuid4(),
            lead_id=lead.id,
            event_type="getcourse.webhook.received",
            source="getcourse",
            payload=normalized["raw_payload"],
        )
    )

    return GetCourseWebhookIngestionResult(lead_id=lead.id, created=created)


def normalize_getcourse_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw_payload = {str(key): _json_safe(value) for key, value in payload.items()}

    email = clean_text(payload.get("email"))
    phone = clean_text(payload.get("phone"))
    first_name = clean_text(payload.get("first_name"))
    last_name = clean_text(payload.get("last_name"))
    full_name = clean_text(payload.get("name")) or join_name(first_name, last_name)

    return {
        "raw_payload": raw_payload,
        "getcourse_user_id": parse_int(payload.get("gc_user_id")),
        "email": email,
        "normalized_email": normalize_email(email),
        "phone": phone,
        "normalized_phone": normalize_phone(phone),
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "city": clean_text(payload.get("city")),
        "country": clean_text(payload.get("country")),
        "source": clean_text(payload.get("source")) or clean_text(payload.get("utm_source")),
        "custom_fields": extract_custom_fields(payload),
        **{key: clean_text(payload.get(key)) for key in UTM_KEYS},
    }


async def find_existing_lead(
    session: AsyncSession,
    getcourse_user_id: int | None,
    normalized_email: str | None,
    normalized_phone: str | None,
) -> Lead | None:
    if getcourse_user_id is not None:
        lead = await session.scalar(select(Lead).where(Lead.getcourse_user_id == getcourse_user_id))
        if lead is not None:
            return lead

    contact_values = [
        ("email", normalized_email),
        ("phone", normalized_phone),
    ]
    for contact_type, normalized_value in contact_values:
        if normalized_value is None:
            continue
        contact = await session.scalar(
            select(LeadContact).where(
                LeadContact.contact_type == contact_type,
                LeadContact.normalized_value == normalized_value,
            )
        )
        if contact is not None:
            return await session.get(Lead, contact.lead_id)

    return None


def apply_payload_to_lead(lead: Lead, normalized: dict[str, Any]) -> None:
    now = datetime.now(UTC)
    lead.getcourse_user_id = normalized["getcourse_user_id"] or lead.getcourse_user_id
    lead.first_name = normalized["first_name"] or lead.first_name
    lead.last_name = normalized["last_name"] or lead.last_name
    lead.full_name = normalized["full_name"] or lead.full_name
    lead.city = normalized["city"] or lead.city
    lead.country = normalized["country"] or lead.country
    lead.source = normalized["source"] or lead.source
    lead.raw_getcourse_data = normalized["raw_payload"]
    lead.updated_at = now


async def upsert_getcourse_external_id(
    session: AsyncSession,
    lead: Lead,
    normalized: dict[str, Any],
) -> None:
    getcourse_user_id = normalized["getcourse_user_id"]
    if getcourse_user_id is None:
        return

    external_id = str(getcourse_user_id)
    item = await session.scalar(
        select(LeadExternalId).where(
            LeadExternalId.provider == "getcourse",
            LeadExternalId.external_id == external_id,
        )
    )
    if item is None:
        session.add(
            LeadExternalId(
                id=uuid.uuid4(),
                lead_id=lead.id,
                provider="getcourse",
                external_id=external_id,
                metadata_=normalized["raw_payload"],
            )
        )
    else:
        item.lead_id = lead.id
        item.metadata_ = normalized["raw_payload"]


async def upsert_contact(
    session: AsyncSession,
    lead: Lead,
    contact_type: str,
    value: str | None,
    normalized_value: str | None,
) -> None:
    if value is None or normalized_value is None:
        return

    contact = await session.scalar(
        select(LeadContact).where(
            LeadContact.contact_type == contact_type,
            LeadContact.normalized_value == normalized_value,
        )
    )
    if contact is None:
        session.add(
            LeadContact(
                id=uuid.uuid4(),
                lead_id=lead.id,
                contact_type=contact_type,
                value=value,
                normalized_value=normalized_value,
                is_primary=True,
            )
        )
        return

    if contact.lead_id == lead.id:
        contact.value = value
        contact.is_primary = True


async def upsert_email_subscription(
    session: AsyncSession,
    lead: Lead,
    normalized: dict[str, Any],
) -> None:
    email = normalized["email"]
    normalized_email = normalized["normalized_email"]
    if email is None or normalized_email is None:
        return

    subscription = await session.scalar(
        select(EmailSubscription).where(EmailSubscription.normalized_email == normalized_email)
    )
    if subscription is None:
        session.add(
            EmailSubscription(
                id=uuid.uuid4(),
                lead_id=lead.id,
                email=email,
                normalized_email=normalized_email,
                status="subscribed",
                subscribed_at=datetime.now(UTC),
            )
        )
    elif subscription.lead_id == lead.id:
        subscription.email = email


async def upsert_custom_fields(
    session: AsyncSession,
    lead: Lead,
    normalized: dict[str, Any],
) -> None:
    for field_key, value in normalized["custom_fields"].items():
        custom_field = await session.scalar(
            select(LeadCustomField).where(
                LeadCustomField.lead_id == lead.id,
                LeadCustomField.source == "getcourse",
                LeadCustomField.field_key == field_key,
            )
        )
        raw_data = {"field_key": field_key, "value": value}
        if custom_field is None:
            session.add(
                LeadCustomField(
                    id=uuid.uuid4(),
                    lead_id=lead.id,
                    source="getcourse",
                    field_key=field_key,
                    field_label=field_key,
                    value=value,
                    normalized_bool=normalize_bool(value),
                    raw_data=raw_data,
                )
            )
        else:
            custom_field.value = value
            custom_field.normalized_bool = normalize_bool(value)
            custom_field.raw_data = raw_data


def has_utm_data(normalized: dict[str, Any]) -> bool:
    return any(normalized[key] is not None for key in UTM_KEYS)


def extract_custom_fields(payload: dict[str, Any]) -> dict[str, str | None]:
    return {
        str(key): clean_text(value)
        for key, value in payload.items()
        if str(key).startswith("custom_")
    }


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if cleaned.lower() in EMPTY_VALUES:
        return None
    return cleaned


def parse_int(value: Any) -> int | None:
    cleaned = clean_text(value)
    if cleaned is None:
        return None
    try:
        return int(cleaned)
    except ValueError as exc:
        raise ValueError("gc_user_id must be an integer.") from exc


def normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip().lower()


def normalize_phone(value: str | None) -> str | None:
    if value is None:
        return None
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) == 11 and digits.startswith("8"):
        digits = f"7{digits[1:]}"
    return digits or None


def normalize_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"yes", "true", "1", "да"}:
        return True
    if normalized in {"no", "false", "0", "нет"}:
        return False
    return None


def join_name(first_name: str | None, last_name: str | None) -> str | None:
    name = " ".join(part for part in (first_name, last_name) if part)
    return name or None


def _json_safe(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)
