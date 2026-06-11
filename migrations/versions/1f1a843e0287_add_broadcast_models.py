"""Add Broadcast models

Revision ID: 1f1a843e0287
Revises: 0004_funnelstate_channel
Create Date: 2026-06-09 20:11:15.431159

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "1f1a843e0287"
down_revision: str | None = "0004_funnelstate_channel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "broadcasts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("segment_query", sa.String(length=1024), nullable=True),
        sa.Column("channels", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("total_leads", sa.Integer(), nullable=False),
        sa.Column("processed_leads", sa.Integer(), nullable=False),
        sa.Column("failed_leads", sa.Integer(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "broadcast_targets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("broadcast_id", sa.UUID(), nullable=False),
        sa.Column("lead_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["broadcast_id"], ["broadcasts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("broadcast_id", "lead_id"),
    )


def downgrade() -> None:
    op.drop_table("broadcast_targets")
    op.drop_table("broadcasts")
