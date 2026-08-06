"""Add durable legacy Telegram migration campaigns.

Revision ID: 20260720_01
Revises: 20260702_02
Create Date: 2026-07-20 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260720_01"
down_revision: str | None = "20260702_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "legacy_telegram_migration_campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="draft"),
        sa.Column("getcourse_field_label", sa.String(length=512), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "legacy_telegram_migration_recipients",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bot_link_token_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.Column("telegram_identity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["bot_link_token_id"], ["bot_link_tokens.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["legacy_telegram_migration_campaigns.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["telegram_identity_id"],
            ["messenger_identities.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bot_link_token_id"),
        sa.UniqueConstraint("campaign_id", "lead_id"),
    )


def downgrade() -> None:
    op.drop_table("legacy_telegram_migration_recipients")
    op.drop_table("legacy_telegram_migration_campaigns")
