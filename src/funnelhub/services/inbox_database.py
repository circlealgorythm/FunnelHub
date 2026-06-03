from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.models import (
    Conversation,
    FunnelState,
    ImportBatch,
    ImportRow,
    Lead,
    LeadContact,
    Message,
    MessengerIdentity,
)
from funnelhub.services.getcourse_webhook import ingest_getcourse_webhook

CSV_EXPORT_COLUMNS = [
    "lead_id",
    "getcourse_user_id",
    "name",
    "first_name",
    "last_name",
    "email",
    "phone",
    "city",
    "country",
    "source",
    "status",
    "telegram",
    "vk",
    "conversations_count",
    "messages_count",
    "created_at",
    "updated_at",
]

IMPORT_FIELD_ALIASES = {
    "gc_user_id": ("gc_user_id", "getcourse_user_id", "id", "ID", "GetCourse ID"),
    "name": ("name", "full_name", "Имя", "ФИО", "Name"),
    "first_name": ("first_name", "Имя пользователя", "First name"),
    "last_name": ("last_name", "Фамилия", "Last name"),
    "email": ("email", "Email", "E-mail", "Почта", "Эл. почта"),
    "phone": ("phone", "Телефон", "Phone", "Номер телефона"),
    "city": ("city", "Город", "City"),
    "country": ("country", "Страна", "Country"),
    "source": ("source", "Источник", "Source"),
    "utm_source": ("utm_source",),
    "utm_medium": ("utm_medium",),
    "utm_campaign": ("utm_campaign",),
    "utm_term": ("utm_term",),
    "utm_content": ("utm_content",),
    "utm_group": ("utm_group",),
}


@dataclass(frozen=True)
class DatabaseLeadSummary:
    id: uuid.UUID
    getcourse_user_id: int | None
    name: str | None
    email: str | None
    phone: str | None
    city: str | None
    country: str | None
    source: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    telegram: str | None
    vk: str | None
    conversations_count: int
    messages_count: int


@dataclass(frozen=True)
class DatabaseLeadDetail:
    lead: DatabaseLeadSummary
    contacts: list[dict[str, Any]]
    identities: list[dict[str, Any]]
    funnel_states: list[dict[str, Any]]
    recent_messages: list[dict[str, Any]]
    raw_getcourse_data: dict[str, Any]


@dataclass(frozen=True)
class DatabaseLeadList:
    items: list[DatabaseLeadSummary]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class DatabaseImportResult:
    batch_id: uuid.UUID
    total_rows: int
    processed_rows: int
    failed_rows: int
    created_rows: int
    updated_rows: int
    errors: list[dict[str, Any]]


async def list_database_leads(
    session: AsyncSession,
    *,
    query: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> DatabaseLeadList:
    clean_query = query.strip() if query else None
    base_statement = build_lead_summary_query()
    count_statement = select(func.count()).select_from(Lead)

    if clean_query:
        search_filter = build_lead_search_filter(clean_query)
        base_statement = base_statement.where(search_filter)
        count_statement = count_statement.where(search_filter)

    total = int(await session.scalar(count_statement) or 0)
    rows = (
        await session.execute(
            base_statement.order_by(Lead.created_at.desc()).limit(limit).offset(offset)
        )
    ).all()
    return DatabaseLeadList(
        items=[row_to_lead_summary(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


async def get_database_lead_detail(
    session: AsyncSession,
    lead_id: uuid.UUID,
) -> DatabaseLeadDetail | None:
    row = (
        await session.execute(build_lead_summary_query().where(Lead.id == lead_id))
    ).one_or_none()
    if row is None:
        return None

    contacts = (
        await session.scalars(
            select(LeadContact)
            .where(LeadContact.lead_id == lead_id)
            .order_by(LeadContact.created_at)
        )
    ).all()
    identities = (
        await session.scalars(
            select(MessengerIdentity)
            .where(MessengerIdentity.lead_id == lead_id)
            .order_by(MessengerIdentity.channel)
        )
    ).all()
    funnel_states = (
        await session.scalars(
            select(FunnelState)
            .where(FunnelState.lead_id == lead_id)
            .order_by(FunnelState.created_at)
        )
    ).all()
    messages = (
        await session.scalars(
            select(Message)
            .where(Message.lead_id == lead_id)
            .order_by(Message.created_at.desc())
            .limit(20)
        )
    ).all()

    lead = await session.get(Lead, lead_id)
    if lead is None:
        return None

    return DatabaseLeadDetail(
        lead=row_to_lead_summary(row),
        contacts=[
            {
                "type": contact.contact_type,
                "value": contact.value,
                "is_primary": contact.is_primary,
                "is_verified": contact.is_verified,
            }
            for contact in contacts
        ],
        identities=[
            {
                "channel": identity.channel,
                "external_user_id": identity.external_user_id,
                "username": identity.username,
                "display_name": identity.display_name,
                "is_subscribed": identity.is_subscribed,
            }
            for identity in identities
        ],
        funnel_states=[
            {
                "funnel_key": state.funnel_key,
                "status": state.status,
                "current_step_key": state.current_step_key,
                "next_run_at": state.next_run_at,
                "completed_at": state.completed_at,
            }
            for state in funnel_states
        ],
        recent_messages=[
            {
                "id": str(message.id),
                "channel": message.channel,
                "direction": message.direction,
                "body": message.body,
                "status": message.status,
                "created_at": message.created_at,
            }
            for message in messages
        ],
        raw_getcourse_data=lead.raw_getcourse_data or {},
    )


async def export_database_leads_csv(session: AsyncSession, *, query: str | None = None) -> str:
    lead_list = await list_database_leads(session, query=query, limit=10_000, offset=0)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_EXPORT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for lead in lead_list.items:
        writer.writerow(lead_export_row(lead))
    return output.getvalue()


async def import_database_leads_csv(
    session: AsyncSession,
    *,
    file_name: str,
    content: bytes,
) -> DatabaseImportResult:
    text = decode_csv_content(content)
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("CSV file must contain a header row.")

    batch = ImportBatch(
        id=uuid.uuid4(),
        source="inbox",
        file_name=file_name,
        file_format="csv",
        encoding="utf-8-sig",
        delimiter=",",
        status="processing",
        metadata_={"fieldnames": reader.fieldnames},
    )
    session.add(batch)
    await session.flush()

    total_rows = 0
    processed_rows = 0
    failed_rows = 0
    created_rows = 0
    updated_rows = 0
    errors: list[dict[str, Any]] = []

    for row_number, row in enumerate(reader, start=2):
        total_rows += 1
        payload = import_row_to_payload(row)
        import_row = ImportRow(
            id=uuid.uuid4(),
            batch_id=batch.id,
            row_number=row_number,
            raw_data={key: value for key, value in row.items() if key is not None},
            errors=[],
        )
        session.add(import_row)

        try:
            if not has_import_identity(payload):
                raise ValueError("Row must include gc_user_id, email, or phone.")
            result = await ingest_getcourse_webhook(session, payload)
            import_row.lead_id = result.lead_id
            import_row.status = "imported"
            processed_rows += 1
            if result.created:
                created_rows += 1
            else:
                updated_rows += 1
        except ValueError as exc:
            failed_rows += 1
            error = {"row_number": row_number, "message": str(exc)}
            import_row.status = "failed"
            import_row.errors = [error]
            errors.append(error)

    batch.total_rows = total_rows
    batch.processed_rows = processed_rows
    batch.failed_rows = failed_rows
    batch.status = "completed" if processed_rows > 0 else "failed"
    batch.metadata_ = {
        **(batch.metadata_ or {}),
        "created_rows": created_rows,
        "updated_rows": updated_rows,
    }
    return DatabaseImportResult(
        batch_id=batch.id,
        total_rows=total_rows,
        processed_rows=processed_rows,
        failed_rows=failed_rows,
        created_rows=created_rows,
        updated_rows=updated_rows,
        errors=errors[:20],
    )


def build_lead_summary_query() -> Select[tuple[Any, ...]]:
    email = lead_contact_subquery("email")
    phone = lead_contact_subquery("phone")
    telegram = messenger_identity_subquery("telegram")
    vk = messenger_identity_subquery("vk")
    conversations_count = (
        select(func.count(Conversation.id))
        .where(Conversation.lead_id == Lead.id)
        .correlate(Lead)
        .scalar_subquery()
    )
    messages_count = (
        select(func.count(Message.id))
        .where(Message.lead_id == Lead.id)
        .correlate(Lead)
        .scalar_subquery()
    )
    return select(
        Lead.id,
        Lead.getcourse_user_id,
        Lead.full_name,
        Lead.first_name,
        Lead.last_name,
        Lead.city,
        Lead.country,
        Lead.source,
        Lead.status,
        Lead.created_at,
        Lead.updated_at,
        email.label("email"),
        phone.label("phone"),
        telegram.label("telegram"),
        vk.label("vk"),
        conversations_count.label("conversations_count"),
        messages_count.label("messages_count"),
    )


def build_lead_search_filter(query: str) -> Any:
    like_query = f"%{query}%"
    lead_filters: list[Any] = [
        Lead.full_name.ilike(like_query),
        Lead.first_name.ilike(like_query),
        Lead.last_name.ilike(like_query),
        Lead.source.ilike(like_query),
    ]
    if query.isdigit():
        lead_filters.append(Lead.getcourse_user_id == int(query))
    contact_match = select(LeadContact.lead_id).where(LeadContact.value.ilike(like_query))
    identity_match = select(MessengerIdentity.lead_id).where(
        or_(
            MessengerIdentity.username.ilike(like_query),
            MessengerIdentity.display_name.ilike(like_query),
            MessengerIdentity.external_user_id.ilike(like_query),
        )
    )
    return or_(
        Lead.id.in_(contact_match),
        Lead.id.in_(identity_match),
        *lead_filters,
        false(),
    )


def lead_contact_subquery(contact_type: str) -> Any:
    return (
        select(LeadContact.value)
        .where(LeadContact.lead_id == Lead.id, LeadContact.contact_type == contact_type)
        .order_by(LeadContact.is_primary.desc(), LeadContact.created_at.asc())
        .limit(1)
        .correlate(Lead)
        .scalar_subquery()
    )


def messenger_identity_subquery(channel: str) -> Any:
    return (
        select(MessengerIdentity.username)
        .where(MessengerIdentity.lead_id == Lead.id, MessengerIdentity.channel == channel)
        .order_by(MessengerIdentity.created_at.desc())
        .limit(1)
        .correlate(Lead)
        .scalar_subquery()
    )


def row_to_lead_summary(row: Any) -> DatabaseLeadSummary:
    name = row.full_name or " ".join(part for part in [row.first_name, row.last_name] if part)
    return DatabaseLeadSummary(
        id=row.id,
        getcourse_user_id=row.getcourse_user_id,
        name=name or None,
        email=row.email,
        phone=row.phone,
        city=row.city,
        country=row.country,
        source=row.source,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        telegram=row.telegram,
        vk=row.vk,
        conversations_count=int(row.conversations_count or 0),
        messages_count=int(row.messages_count or 0),
    )


def lead_export_row(lead: DatabaseLeadSummary) -> dict[str, Any]:
    return {
        "lead_id": str(lead.id),
        "getcourse_user_id": lead.getcourse_user_id,
        "name": lead.name,
        "first_name": "",
        "last_name": "",
        "email": lead.email,
        "phone": lead.phone,
        "city": lead.city,
        "country": lead.country,
        "source": lead.source,
        "status": lead.status,
        "telegram": lead.telegram,
        "vk": lead.vk,
        "conversations_count": lead.conversations_count,
        "messages_count": lead.messages_count,
        "created_at": lead.created_at.isoformat(),
        "updated_at": lead.updated_at.isoformat(),
    }


def decode_csv_content(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV file encoding must be UTF-8 or Windows-1251.")


def import_row_to_payload(row: dict[str, str | None]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for target_key, aliases in IMPORT_FIELD_ALIASES.items():
        value = first_row_value(row, aliases)
        if value is not None:
            payload[target_key] = value

    for key, value in row.items():
        if key is not None and key.startswith("custom_") and clean_import_value(value) is not None:
            payload[key] = clean_import_value(value)

    return payload


def first_row_value(row: dict[str, str | None], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = clean_import_value(row.get(key))
        if value is not None:
            return value
    return None


def clean_import_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def has_import_identity(payload: dict[str, Any]) -> bool:
    return any(payload.get(key) for key in ("gc_user_id", "email", "phone"))
