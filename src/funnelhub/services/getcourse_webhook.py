from __future__ import annotations

import re
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
    LeadConsent,
    LeadContact,
    LeadCustomField,
    LeadExternalId,
    LeadUtm,
)
from funnelhub.services.bot_linking import create_or_get_active_bot_link_token
from funnelhub.services.email_messaging import ensure_email_unsubscribe_token

EMPTY_VALUES = {"", "(empty)", "none", "null"}
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_group")
PROFILE_FIELD_ALIASES = {
    "registration_type": ("registration_type", "registration", "Тип регистрации"),
    "getcourse_created_at": ("getcourse_created_at", "created_at", "created", "Создан"),
    "getcourse_last_activity_at": (
        "getcourse_last_activity_at",
        "last_activity_at",
        "last_activity",
        "Последняя активность",
    ),
    "source": ("source", "Источник", "Откуда пришел"),
}
KNOWN_ADDITIONAL_FIELD_ALIASES = {
    "birth_date": ("birth_date", "birthday", "Дата рождения", "День рождения"),
    "age": ("age", "Возраст"),
    "gender": ("gender", "Пол"),
    "note": ("note", "comment", "Примечание"),
    "partner": ("partner", "От партнера"),
    "partner_id": ("partner_id", "ID партнера"),
    "partner_email": ("partner_email", "Email партнера"),
    "partner_name": ("partner_name", "ФИО партнера"),
    "manager_name": ("manager_name", "ФИО менеджера"),
    "vk_id": (
        "vk_id",
        "vk_user_id",
        "VK-ID",
        "VK ID",
        "ID VK",
        "ВК-ID",
        "ID ВК",
        "ID ВКонтакте",
        "Профиль ВКонтакте",
    ),
    "getcourse_groups": (
        "getcourse_groups",
        "group_ids",
        "groups",
        "id групп пользователя/дата добавления",
    ),
    "mailing_categories": ("mailing_categories", "Категории рассылок"),
}
ADDITIONAL_FIELD_LABELS = {
    "birth_date": "Дата рождения",
    "age": "Возраст",
    "gender": "Пол",
    "note": "Примечание",
    "partner": "От партнера",
    "partner_id": "ID партнера",
    "partner_email": "Email партнера",
    "partner_name": "ФИО партнера",
    "manager_name": "ФИО менеджера",
    "vk_id": "VK-ID",
    "getcourse_groups": "Группы GetCourse",
    "mailing_categories": "Категории рассылок",
}
PRIVACY_POLICY_URL = "https://shamanaisu.getcourse.ru/politica"
CONSENT_CUSTOM_FIELD_MAPPING = {
    "custom_10558670": "https://shamanaisu.getcourse.ru/oferta",
    "custom_10575005": "https://school.aisukam.ru/oferta_old",
    "custom_10616540": None,
    "custom_10661024": "https://school.aisukam.ru/oferta_marafon_meditation",
    "custom_10682753": "https://school.aisukam.ru/oferta_orakuly",
    "custom_10682754": "https://school.aisukam.ru/oferta_skoraya_pomoshch",
    "custom_10683365": "https://school.aisukam.ru/oferta_individualnoe_nastavnichestvo",
    "custom_11344348": "https://school.aisukam.ru/oferta_shamanputesh",
}
CONSENT_CUSTOM_FIELD_LABELS = {
    field_key: (
        "Я согласен (-на) на обработку моих персональных данных "
        "в соответствии с Политикой конфиденциальности"
        + (" и Договором оферты" if offer_url is not None else "")
    )
    for field_key, offer_url in CONSENT_CUSTOM_FIELD_MAPPING.items()
}


@dataclass(frozen=True)
class GetCourseWebhookIngestionResult:
    lead_id: uuid.UUID
    created: bool
    bot_link_token: str


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
    await upsert_optional_external_ids(session, lead, normalized)
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
    custom_fields = await upsert_custom_fields(session, lead, normalized)
    await upsert_consents(session, lead, custom_fields)

    if has_utm_data(normalized["utm"]):
        session.add(
            LeadUtm(
                id=uuid.uuid4(),
                lead_id=lead.id,
                source_kind="form",
                utm_source=normalized["utm"]["utm_source"],
                utm_medium=normalized["utm"]["utm_medium"],
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

    bot_link_token = await create_or_get_active_bot_link_token(session, lead)
    return GetCourseWebhookIngestionResult(
        lead_id=lead.id,
        created=created,
        bot_link_token=bot_link_token.token,
    )


def normalize_getcourse_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw_payload = {str(key): _json_safe(value) for key, value in payload.items()}

    email = clean_text(first_payload_value(payload, ("email", "Email", "E-mail")))
    phone = clean_text(first_payload_value(payload, ("phone", "Телефон", "Phone")))
    first_name = clean_text(first_payload_value(payload, ("first_name", "Имя", "Имя пользователя")))
    last_name = clean_text(first_payload_value(payload, ("last_name", "Фамилия")))
    full_name = clean_text(
        first_payload_value(payload, ("name", "full_name", "ФИО"))
    ) or join_name(first_name, last_name)
    regular_utm = {key: clean_text(payload.get(key)) for key in UTM_KEYS}
    additional_fields = extract_custom_fields(payload)
    additional_fields.update(extract_known_additional_fields(payload))
    vk_id = normalize_vk_external_id(additional_fields.get("vk_id"))
    if vk_id is not None:
        additional_fields["vk_id"] = vk_id
    else:
        additional_fields.pop("vk_id", None)

    return {
        "raw_payload": raw_payload,
        "getcourse_user_id": parse_int(
            first_payload_value(payload, ("gc_user_id", "getcourse_user_id", "id", "ID"))
        ),
        "email": email,
        "normalized_email": normalize_email(email),
        "phone": phone,
        "normalized_phone": normalize_phone(phone),
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "city": clean_text(first_payload_value(payload, ("city", "Город", "City"))),
        "country": clean_text(first_payload_value(payload, ("country", "Страна", "Country"))),
        "registration_type": clean_text(
            first_payload_value(payload, PROFILE_FIELD_ALIASES["registration_type"])
        ),
        "getcourse_created_at": parse_datetime(
            first_payload_value(payload, PROFILE_FIELD_ALIASES["getcourse_created_at"])
        ),
        "getcourse_last_activity_at": parse_datetime(
            first_payload_value(payload, PROFILE_FIELD_ALIASES["getcourse_last_activity_at"])
        ),
        "source": clean_text(first_payload_value(payload, PROFILE_FIELD_ALIASES["source"]))
        or regular_utm["utm_source"],
        "custom_fields": additional_fields,
        "utm": regular_utm,
        **regular_utm,
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
    lead.registration_type = normalized["registration_type"] or lead.registration_type
    lead.getcourse_created_at = normalized["getcourse_created_at"] or lead.getcourse_created_at
    lead.getcourse_last_activity_at = (
        normalized["getcourse_last_activity_at"] or lead.getcourse_last_activity_at
    )
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


async def upsert_optional_external_ids(
    session: AsyncSession,
    lead: Lead,
    normalized: dict[str, Any],
) -> None:
    custom_fields = normalized["custom_fields"]
    vk_id = custom_fields.get("vk_id")
    if vk_id is not None:
        await upsert_external_id(
            session=session,
            lead=lead,
            provider="getcourse_vk_id",
            external_id=vk_id,
            metadata=normalized["raw_payload"],
        )


async def upsert_external_id(
    session: AsyncSession,
    lead: Lead,
    provider: str,
    external_id: str,
    metadata: dict[str, Any],
) -> None:
    item = await session.scalar(
        select(LeadExternalId).where(
            LeadExternalId.provider == provider,
            LeadExternalId.external_id == external_id,
        )
    )
    if item is None:
        session.add(
            LeadExternalId(
                id=uuid.uuid4(),
                lead_id=lead.id,
                provider=provider,
                external_id=external_id,
                metadata_=metadata,
            )
        )
        return

    item.lead_id = lead.id
    item.metadata_ = metadata


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
        subscription = EmailSubscription(
            id=uuid.uuid4(),
            lead_id=lead.id,
            email=email,
            normalized_email=normalized_email,
            status="subscribed",
            subscribed_at=datetime.now(UTC),
        )
        session.add(subscription)
        await ensure_email_unsubscribe_token(session, subscription)
    elif subscription.lead_id == lead.id:
        subscription.email = email
        await ensure_email_unsubscribe_token(session, subscription)


async def upsert_custom_fields(
    session: AsyncSession,
    lead: Lead,
    normalized: dict[str, Any],
) -> dict[str, LeadCustomField]:
    custom_fields = {}
    for field_key, value in normalized["custom_fields"].items():
        custom_field = await session.scalar(
            select(LeadCustomField).where(
                LeadCustomField.lead_id == lead.id,
                LeadCustomField.source == "getcourse",
                LeadCustomField.field_key == field_key,
            )
        )
        raw_data = {"field_key": field_key, "value": value}
        field_label = human_custom_field_label(field_key)
        if custom_field is None:
            custom_field = LeadCustomField(
                id=uuid.uuid4(),
                lead_id=lead.id,
                source="getcourse",
                field_key=field_key,
                field_label=field_label,
                value=value,
                normalized_bool=normalize_bool(value),
                raw_data=raw_data,
            )
            session.add(custom_field)
        else:
            custom_field.field_label = field_label
            custom_field.value = value
            custom_field.normalized_bool = normalize_bool(value)
            custom_field.raw_data = raw_data
        custom_fields[field_key] = custom_field

    return custom_fields


async def upsert_consents(
    session: AsyncSession,
    lead: Lead,
    custom_fields: dict[str, LeadCustomField],
) -> None:
    for field_key, custom_field in custom_fields.items():
        if (
            custom_field.normalized_bool is not True
            or field_key not in CONSENT_CUSTOM_FIELD_MAPPING
        ):
            continue

        offer_url = CONSENT_CUSTOM_FIELD_MAPPING[field_key]
        await upsert_consent(
            session=session,
            lead=lead,
            custom_field=custom_field,
            consent_type="personal_data",
            metadata={
                "privacy_policy_url": PRIVACY_POLICY_URL,
            },
        )
        await upsert_consent(
            session=session,
            lead=lead,
            custom_field=custom_field,
            consent_type="privacy_policy",
            metadata={
                "privacy_policy_url": PRIVACY_POLICY_URL,
            },
        )

        if offer_url is not None:
            await upsert_consent(
                session=session,
                lead=lead,
                custom_field=custom_field,
                consent_type="offer_agreement",
                metadata={
                    "offer_url": offer_url,
                    "privacy_policy_url": PRIVACY_POLICY_URL,
                },
            )


async def upsert_consent(
    session: AsyncSession,
    lead: Lead,
    custom_field: LeadCustomField,
    consent_type: str,
    metadata: dict[str, Any],
) -> None:
    now = datetime.now(UTC)
    consent = await session.scalar(
        select(LeadConsent).where(
            LeadConsent.lead_id == lead.id,
            LeadConsent.consent_type == consent_type,
            LeadConsent.source == "getcourse",
        )
    )
    merged_metadata = merge_consent_metadata(
        existing=consent.metadata_ if consent is not None else {},
        custom_field=custom_field,
        metadata=metadata,
    )
    if consent is None:
        session.add(
            LeadConsent(
                id=uuid.uuid4(),
                lead_id=lead.id,
                consent_type=consent_type,
                is_granted=True,
                granted_at=now,
                source="getcourse",
                source_custom_field_id=custom_field.id,
                metadata_=merged_metadata,
            )
        )
        return

    consent.is_granted = True
    consent.granted_at = consent.granted_at or now
    consent.revoked_at = None
    consent.source_custom_field_id = custom_field.id
    consent.metadata_ = merged_metadata


def merge_consent_metadata(
    existing: dict[str, Any],
    custom_field: LeadCustomField,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    merged = {**existing, **metadata}

    custom_field_keys = list(merged.get("custom_field_keys", []))
    if custom_field.field_key not in custom_field_keys:
        custom_field_keys.append(custom_field.field_key)
    merged["custom_field_keys"] = custom_field_keys

    offer_url = metadata.get("offer_url")
    if isinstance(offer_url, str):
        offer_urls = list(merged.get("offer_urls", []))
        if offer_url not in offer_urls:
            offer_urls.append(offer_url)
        merged["offer_urls"] = offer_urls

    return merged


def has_utm_data(values: dict[str, str | None]) -> bool:
    return any(values.get(key) is not None for key in UTM_KEYS)


def extract_custom_fields(payload: dict[str, Any]) -> dict[str, str | None]:
    return {
        str(key): clean_text(value)
        for key, value in payload.items()
        if str(key).startswith("custom_")
    }


def extract_known_additional_fields(payload: dict[str, Any]) -> dict[str, str | None]:
    fields: dict[str, str | None] = {}
    for field_key, aliases in KNOWN_ADDITIONAL_FIELD_ALIASES.items():
        value = clean_text(first_payload_value(payload, aliases))
        if value is not None:
            fields[field_key] = value
    return fields


def first_payload_value(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = payload.get(key)
        if clean_text(value) is not None:
            return value
    return None


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


def parse_datetime(value: Any) -> datetime | None:
    cleaned = clean_text(value)
    if cleaned is None:
        return None
    normalized = cleaned.replace("T", " ")
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid datetime value: {cleaned}") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


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


def normalize_vk_external_id(value: str | None) -> str | None:
    cleaned = clean_text(value)
    if cleaned is None:
        return None
    if cleaned.isdigit() and int(cleaned) > 0:
        return str(int(cleaned))

    match = re.search(r"(?:^|[/\s])id(\d+)(?:\D|$)", cleaned, flags=re.IGNORECASE)
    if match is None:
        return None
    normalized = match.group(1)
    if int(normalized) <= 0:
        return None
    return str(int(normalized))


def join_name(first_name: str | None, last_name: str | None) -> str | None:
    name = " ".join(part for part in (first_name, last_name) if part)
    return name or None


def human_custom_field_label(field_key: str) -> str:
    if field_key in ADDITIONAL_FIELD_LABELS:
        return ADDITIONAL_FIELD_LABELS[field_key]
    if field_key in CONSENT_CUSTOM_FIELD_LABELS:
        return CONSENT_CUSTOM_FIELD_LABELS[field_key]
    return field_key


def _json_safe(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)
