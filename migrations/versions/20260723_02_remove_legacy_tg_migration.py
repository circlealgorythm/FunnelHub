"""Remove the cancelled legacy Telegram/VK migration feature and its data.

Revision ID: 20260723_02
Revises: 20260723_01
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260723_02"
down_revision: str | None = "20260723_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A migration recipient can be an older Inbox lead that was matched by contact data.
    # Delete only leads created with the migration and without any independent Inbox activity.
    op.execute(
        sa.text(
            """
            DELETE FROM leads AS lead
            USING legacy_telegram_migration_recipients AS recipient,
                  legacy_telegram_migration_campaigns AS campaign
            WHERE lead.id = recipient.lead_id
              AND recipient.campaign_id = campaign.id
              AND lead.created_at >= campaign.created_at - INTERVAL '1 hour'
              AND NOT EXISTS (
                SELECT 1 FROM messenger_identities identity
                WHERE identity.lead_id = lead.id
              )
              AND NOT EXISTS (
                SELECT 1 FROM funnel_states state
                WHERE state.lead_id = lead.id
              )
              AND NOT EXISTS (
                SELECT 1 FROM conversations conversation
                WHERE conversation.lead_id = lead.id
              )
              AND NOT EXISTS (
                SELECT 1 FROM broadcast_targets target
                WHERE target.lead_id = lead.id
              )
              AND NOT EXISTS (
                SELECT 1 FROM followup_deliveries delivery
                WHERE delivery.lead_id = lead.id
              )
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM lead_custom_fields
            WHERE source = 'legacy_tg_migration'
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM bot_link_tokens
            WHERE metadata ->> 'legacy_tg_migration_campaign_id' IN (
                SELECT id::text FROM legacy_telegram_migration_campaigns
            )
            """
        )
    )
    op.drop_table("legacy_telegram_migration_recipients")
    op.drop_table("legacy_telegram_migration_campaigns")


def downgrade() -> None:
    op.create_table(
        "legacy_telegram_migration_campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="draft"),
        sa.Column("getcourse_field_label", sa.String(length=512), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "legacy_telegram_migration_recipients",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bot_link_token_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("channel", sa.String(length=32), nullable=False, server_default="telegram"),
        sa.Column("audience_kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="pending"),
        sa.Column("sync_stage", sa.String(length=32), nullable=True),
        sa.Column(
            "getcourse_sync_status",
            sa.String(length=64),
            nullable=False,
            server_default="not_synced",
        ),
        sa.Column("sync_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.Column("getcourse_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("messenger_identity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["bot_link_token_id"], ["bot_link_tokens.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["legacy_telegram_migration_campaigns.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["messenger_identity_id"],
            ["messenger_identities.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bot_link_token_id"),
        sa.UniqueConstraint("campaign_id", "lead_id"),
    )
    op.create_index(
        "ix_legacy_migration_recipient_channel",
        "legacy_telegram_migration_recipients",
        ["campaign_id", "channel"],
    )
