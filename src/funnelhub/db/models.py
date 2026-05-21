from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from funnelhub.db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Lead(Base, TimestampMixin):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    getcourse_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(512))
    country: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(255))
    registration_type: Mapped[str | None] = mapped_column(String(255))
    source: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(64), default="new", nullable=False)
    getcourse_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    getcourse_last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_from_getcourse_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_getcourse_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    contacts: Mapped[list[LeadContact]] = relationship(back_populates="lead")


class LeadContact(Base, TimestampMixin):
    __tablename__ = "lead_contacts"
    __table_args__ = (UniqueConstraint("contact_type", "normalized_value"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"))
    contact_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(512), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    lead: Mapped[Lead] = relationship(back_populates="contacts")


class LeadExternalId(Base, TimestampMixin):
    __tablename__ = "lead_external_ids"
    __table_args__ = (UniqueConstraint("provider", "external_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )


class LeadUtm(Base, TimestampMixin):
    __tablename__ = "lead_utm"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"))
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    utm_source: Mapped[str | None] = mapped_column(String(255))
    utm_medium: Mapped[str | None] = mapped_column(String(255))
    utm_campaign: Mapped[str | None] = mapped_column(String(255))
    utm_term: Mapped[str | None] = mapped_column(String(255))
    utm_content: Mapped[str | None] = mapped_column(String(512))
    utm_group: Mapped[str | None] = mapped_column(String(255))
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class LeadCustomField(Base, TimestampMixin):
    __tablename__ = "lead_custom_fields"
    __table_args__ = (UniqueConstraint("lead_id", "source", "field_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(64), default="getcourse", nullable=False)
    field_key: Mapped[str] = mapped_column(String(255), nullable=False)
    field_label: Mapped[str | None] = mapped_column(String(1024))
    field_position: Mapped[int | None] = mapped_column(Integer)
    value: Mapped[str | None] = mapped_column(Text)
    normalized_bool: Mapped[bool | None] = mapped_column(Boolean)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class LeadConsent(Base, TimestampMixin):
    __tablename__ = "lead_consents"
    __table_args__ = (UniqueConstraint("lead_id", "consent_type", "source"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"))
    consent_type: Mapped[str] = mapped_column(String(64), nullable=False)
    is_granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(64), default="getcourse", nullable=False)
    source_custom_field_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lead_custom_fields.id", ondelete="SET NULL")
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )


class MessengerIdentity(Base, TimestampMixin):
    __tablename__ = "messenger_identities"
    __table_args__ = (UniqueConstraint("channel", "external_user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    external_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(512))
    is_subscribed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    subscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_profile: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class EmailSubscription(Base, TimestampMixin):
    __tablename__ = "email_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"))
    email: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="subscribed", nullable=False)
    subscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unsubscribe_token: Mapped[str | None] = mapped_column(String(255), unique=True)
    provider: Mapped[str | None] = mapped_column(String(64))
    provider_contact_id: Mapped[str | None] = mapped_column(String(255))


class FunnelState(Base, TimestampMixin):
    __tablename__ = "funnel_states"
    __table_args__ = (UniqueConstraint("lead_id", "funnel_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"))
    funnel_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="active", nullable=False)
    current_step_key: Mapped[str | None] = mapped_column(String(255))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="open", nullable=False)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base, TimestampMixin):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL")
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), default="text", nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    external_message_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(64), default="created", nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )


class ImportBatch(Base, TimestampMixin):
    __tablename__ = "import_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    source: Mapped[str] = mapped_column(String(64), default="getcourse", nullable=False)
    file_name: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_format: Mapped[str] = mapped_column(String(32), nullable=False)
    encoding: Mapped[str | None] = mapped_column(String(64))
    delimiter: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(64), default="created", nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )


class ImportRow(Base, TimestampMixin):
    __tablename__ = "import_rows"
    __table_args__ = (UniqueConstraint("batch_id", "row_number"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"))
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"))
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="created", nullable=False)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)


class Event(Base, TimestampMixin):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    dedupe_key: Mapped[str | None] = mapped_column(String(512), unique=True)
