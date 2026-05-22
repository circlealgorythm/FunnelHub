"""bot link tokens

Revision ID: 0002_bot_link_tokens
Revises: 0001_core_data_model
Create Date: 2026-05-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_bot_link_tokens"
down_revision: str | None = "0001_core_data_model"
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
    op.create_table(
        "bot_link_tokens",
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
        sa.Column("token", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        *create_timestamp_columns(),
        sa.CheckConstraint(
            "status IN ('active', 'used', 'expired', 'revoked')",
            name="ck_bot_link_tokens_status",
        ),
        sa.UniqueConstraint("token", name="uq_bot_link_tokens_token"),
    )
    op.create_index("ix_bot_link_tokens_lead_id", "bot_link_tokens", ["lead_id"])
    op.create_index(
        "ix_bot_link_tokens_status_expires",
        "bot_link_tokens",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_table("bot_link_tokens")
