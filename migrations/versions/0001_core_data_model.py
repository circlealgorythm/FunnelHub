"""core data model

Revision ID: 0001_core_data_model
Revises:
Create Date: 2026-05-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_core_data_model"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def create_timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "leads",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("getcourse_user_id", sa.BigInteger(), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=512), nullable=True),
        sa.Column("country", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=255), nullable=True),
        sa.Column("registration_type", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="new"),
        sa.Column("getcourse_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("getcourse_last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_from_getcourse_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "raw_getcourse_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        *create_timestamp_columns(),
        sa.CheckConstraint(
            "status IN ('new', 'active', 'customer', 'archived', 'unsubscribed')",
            name="ck_leads_status",
        ),
        sa.UniqueConstraint("getcourse_user_id", name="uq_leads_getcourse_user_id"),
    )
    op.create_index("ix_leads_created_at", "leads", ["created_at"])
    op.create_index("ix_leads_status", "leads", ["status"])

    op.create_table(
        "lead_contacts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("contact_type", sa.String(length=32), nullable=False),
        sa.Column("value", sa.String(length=512), nullable=False),
        sa.Column("normalized_value", sa.String(length=512), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *create_timestamp_columns(),
        sa.CheckConstraint("contact_type IN ('email', 'phone')", name="ck_lead_contacts_type"),
        sa.UniqueConstraint(
            "contact_type", "normalized_value", name="uq_lead_contacts_type_normalized"
        ),
    )
    op.create_index("ix_lead_contacts_lead_id", "lead_contacts", ["lead_id"])

    op.create_table(
        "lead_external_ids",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column(
            "metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        *create_timestamp_columns(),
        sa.UniqueConstraint(
            "provider", "external_id", name="uq_lead_external_ids_provider_external_id"
        ),
    )
    op.create_index("ix_lead_external_ids_lead_id", "lead_external_ids", ["lead_id"])

    op.create_table(
        "lead_utm",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("utm_source", sa.String(length=255), nullable=True),
        sa.Column("utm_medium", sa.String(length=255), nullable=True),
        sa.Column("utm_campaign", sa.String(length=255), nullable=True),
        sa.Column("utm_term", sa.String(length=255), nullable=True),
        sa.Column("utm_content", sa.String(length=512), nullable=True),
        sa.Column("utm_group", sa.String(length=255), nullable=True),
        sa.Column(
            "raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        *create_timestamp_columns(),
        sa.CheckConstraint(
            "source_kind IN ('getcourse_system', 'form', 'import', 'manual')",
            name="ck_lead_utm_source_kind",
        ),
    )
    op.create_index("ix_lead_utm_lead_id", "lead_utm", ["lead_id"])
    op.create_index("ix_lead_utm_source_campaign", "lead_utm", ["utm_source", "utm_campaign"])

    op.create_table(
        "lead_custom_fields",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="getcourse"),
        sa.Column("field_key", sa.String(length=255), nullable=False),
        sa.Column("field_label", sa.String(length=1024), nullable=True),
        sa.Column("field_position", sa.Integer(), nullable=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("normalized_bool", sa.Boolean(), nullable=True),
        sa.Column(
            "raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        *create_timestamp_columns(),
        sa.UniqueConstraint(
            "lead_id", "source", "field_key", name="uq_lead_custom_fields_lead_source_key"
        ),
    )
    op.create_index("ix_lead_custom_fields_lead_id", "lead_custom_fields", ["lead_id"])
    op.create_index(
        "ix_lead_custom_fields_key_bool", "lead_custom_fields", ["field_key", "normalized_bool"]
    )

    op.create_table(
        "lead_consents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("consent_type", sa.String(length=64), nullable=False),
        sa.Column("is_granted", sa.Boolean(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="getcourse"),
        sa.Column(
            "source_custom_field_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lead_custom_fields.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        *create_timestamp_columns(),
        sa.CheckConstraint(
            "consent_type IN ("
            "'privacy_policy', 'offer_agreement', 'personal_data', "
            "'email_marketing', 'messenger_marketing', 'other'"
            ")",
            name="ck_lead_consents_type",
        ),
        sa.UniqueConstraint(
            "lead_id", "consent_type", "source", name="uq_lead_consents_lead_type_source"
        ),
    )
    op.create_index("ix_lead_consents_lead_id", "lead_consents", ["lead_id"])

    op.create_table(
        "messenger_identities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("external_user_id", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=512), nullable=True),
        sa.Column("is_subscribed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("subscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "raw_profile",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        *create_timestamp_columns(),
        sa.CheckConstraint(
            "channel IN ('telegram', 'vk', 'max')", name="ck_messenger_identities_channel"
        ),
        sa.UniqueConstraint(
            "channel", "external_user_id", name="uq_messenger_identities_channel_external_user_id"
        ),
    )
    op.create_index("ix_messenger_identities_lead_id", "messenger_identities", ["lead_id"])
    op.create_index(
        "ix_messenger_identities_channel_subscribed",
        "messenger_identities",
        ["channel", "is_subscribed"],
    )

    op.create_table(
        "email_subscriptions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=512), nullable=False),
        sa.Column("normalized_email", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="subscribed"),
        sa.Column("subscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unsubscribe_token", sa.String(length=255), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("provider_contact_id", sa.String(length=255), nullable=True),
        *create_timestamp_columns(),
        sa.CheckConstraint(
            "status IN ('subscribed', 'unsubscribed', 'bounced', 'complained', 'suppressed')",
            name="ck_email_subscriptions_status",
        ),
        sa.UniqueConstraint("normalized_email", name="uq_email_subscriptions_normalized_email"),
        sa.UniqueConstraint("unsubscribe_token", name="uq_email_subscriptions_unsubscribe_token"),
    )
    op.create_index("ix_email_subscriptions_lead_id", "email_subscriptions", ["lead_id"])
    op.create_index("ix_email_subscriptions_status", "email_subscriptions", ["status"])

    op.create_table(
        "funnel_states",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("funnel_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="active"),
        sa.Column("current_step_key", sa.String(length=255), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        *create_timestamp_columns(),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'completed', 'stopped')", name="ck_funnel_states_status"
        ),
        sa.UniqueConstraint("lead_id", "funnel_key", name="uq_funnel_states_lead_funnel_key"),
    )
    op.create_index("ix_funnel_states_next_run_at", "funnel_states", ["next_run_at"])
    op.create_index("ix_funnel_states_status", "funnel_states", ["status"])

    op.create_table(
        "conversations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="open"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        *create_timestamp_columns(),
        sa.CheckConstraint(
            "channel IN ('telegram', 'vk', 'max', 'email')", name="ck_conversations_channel"
        ),
        sa.CheckConstraint(
            "status IN ('open', 'pending', 'closed')", name="ck_conversations_status"
        ),
    )
    op.create_index("ix_conversations_lead_id", "conversations", ["lead_id"])
    op.create_index(
        "ix_conversations_status_last_message", "conversations", ["status", "last_message_at"]
    )

    op.create_table(
        "messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("message_type", sa.String(length=32), nullable=False, server_default="text"),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("external_message_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="created"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        *create_timestamp_columns(),
        sa.CheckConstraint(
            "channel IN ('telegram', 'vk', 'max', 'email')", name="ck_messages_channel"
        ),
        sa.CheckConstraint("direction IN ('inbound', 'outbound')", name="ck_messages_direction"),
        sa.CheckConstraint(
            "status IN ('created', 'queued', 'sent', 'delivered', 'read', 'failed')",
            name="ck_messages_status",
        ),
    )
    op.create_index("ix_messages_lead_id", "messages", ["lead_id"])
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index(
        "ix_messages_channel_external_id", "messages", ["channel", "external_message_id"]
    )

    op.create_table(
        "import_batches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="getcourse"),
        sa.Column("file_name", sa.String(length=1024), nullable=False),
        sa.Column("file_format", sa.String(length=32), nullable=False),
        sa.Column("encoding", sa.String(length=64), nullable=True),
        sa.Column("delimiter", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="created"),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        *create_timestamp_columns(),
        sa.CheckConstraint(
            "status IN ('created', 'processing', 'completed', 'failed')",
            name="ck_import_batches_status",
        ),
    )

    op.create_table(
        "import_rows",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("import_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="created"),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "errors", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"
        ),
        *create_timestamp_columns(),
        sa.CheckConstraint(
            "status IN ('created', 'imported', 'skipped', 'failed')", name="ck_import_rows_status"
        ),
        sa.UniqueConstraint("batch_id", "row_number", name="uq_import_rows_batch_row_number"),
    )
    op.create_index("ix_import_rows_batch_id", "import_rows", ["batch_id"])
    op.create_index("ix_import_rows_lead_id", "import_rows", ["lead_id"])

    op.create_table(
        "events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column("dedupe_key", sa.String(length=512), nullable=True),
        *create_timestamp_columns(),
        sa.UniqueConstraint("dedupe_key", name="uq_events_dedupe_key"),
    )
    op.create_index("ix_events_lead_id", "events", ["lead_id"])
    op.create_index("ix_events_type_occurred_at", "events", ["event_type", "occurred_at"])


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("import_rows")
    op.drop_table("import_batches")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("funnel_states")
    op.drop_table("email_subscriptions")
    op.drop_table("messenger_identities")
    op.drop_table("lead_consents")
    op.drop_table("lead_custom_fields")
    op.drop_table("lead_utm")
    op.drop_table("lead_external_ids")
    op.drop_table("lead_contacts")
    op.drop_table("leads")
