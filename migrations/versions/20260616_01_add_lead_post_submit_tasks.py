"""Add lead post-submit task table

Revision ID: 20260616_01
Revises: 20260612_01
Create Date: 2026-06-16 18:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260616_01"
down_revision: str | None = "20260612_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lead_post_submit_tasks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("lead_id", sa.UUID(), nullable=False),
        sa.Column("task_type", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=512), nullable=True),
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
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index(
        "ix_lead_post_submit_tasks_due",
        "lead_post_submit_tasks",
        ["status", "not_before"],
    )
    op.create_index(
        "ix_lead_post_submit_tasks_lead_type",
        "lead_post_submit_tasks",
        ["lead_id", "task_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_lead_post_submit_tasks_lead_type", table_name="lead_post_submit_tasks")
    op.drop_index("ix_lead_post_submit_tasks_due", table_name="lead_post_submit_tasks")
    op.drop_table("lead_post_submit_tasks")
