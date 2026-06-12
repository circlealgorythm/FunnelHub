"""Add follow-up post tables

Revision ID: 20260612_01
Revises: 20260611_01
Create Date: 2026-06-12 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260612_01"
down_revision: str | None = "20260611_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "followup_posts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("channels", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_autopost_id", sa.UUID(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_deliveries", sa.Integer(), nullable=False),
        sa.Column("sent_deliveries", sa.Integer(), nullable=False),
        sa.Column("failed_deliveries", sa.Integer(), nullable=False),
        sa.Column("skipped_deliveries", sa.Integer(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["source_autopost_id"], ["autoposts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index(
        "ix_followup_posts_status_scheduled",
        "followup_posts",
        ["status", "scheduled_at"],
    )

    op.create_table(
        "followup_deliveries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("followup_post_id", sa.UUID(), nullable=False),
        sa.Column("lead_id", sa.UUID(), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("messenger_identity_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("external_message_id", sa.String(length=255), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["followup_post_id"], ["followup_posts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["messenger_identity_id"], ["messenger_identities.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("followup_post_id", "lead_id", "channel"),
    )
    op.create_index(
        "ix_followup_deliveries_post_status",
        "followup_deliveries",
        ["followup_post_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_followup_deliveries_post_status", table_name="followup_deliveries")
    op.drop_table("followup_deliveries")
    op.drop_index("ix_followup_posts_status_scheduled", table_name="followup_posts")
    op.drop_table("followup_posts")
