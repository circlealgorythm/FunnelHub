"""Add available_at to follow-up deliveries

Revision ID: 20260702_01
Revises: 20260616_01
Create Date: 2026-07-02 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260702_01"
down_revision: str | None = "20260616_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "followup_deliveries",
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE followup_deliveries "
        "SET available_at = COALESCE(sent_at, attempted_at, created_at, now()) "
        "WHERE available_at IS NULL"
    )
    op.alter_column("followup_deliveries", "available_at", nullable=False)
    op.create_index(
        "ix_followup_deliveries_status_available",
        "followup_deliveries",
        ["status", "available_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_followup_deliveries_status_available", table_name="followup_deliveries")
    op.drop_column("followup_deliveries", "available_at")
