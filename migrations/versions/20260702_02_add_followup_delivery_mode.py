"""Add delivery mode to follow-up posts

Revision ID: 20260702_02
Revises: 20260702_01
Create Date: 2026-07-02 13:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260702_02"
down_revision: str | None = "20260702_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "followup_posts",
        sa.Column("delivery_mode", sa.String(length=32), nullable=True),
    )
    op.execute("UPDATE followup_posts SET delivery_mode = 'queued' WHERE delivery_mode IS NULL")
    op.alter_column("followup_posts", "delivery_mode", nullable=False)


def downgrade() -> None:
    op.drop_column("followup_posts", "delivery_mode")
