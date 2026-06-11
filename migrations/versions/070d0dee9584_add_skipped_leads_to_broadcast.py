"""Add skipped_leads to Broadcast

Revision ID: 070d0dee9584
Revises: 1f1a843e0287
Create Date: 2026-06-09 20:33:10.951227

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '070d0dee9584'
down_revision: str | None = '1f1a843e0287'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "broadcasts",
        sa.Column("skipped_leads", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("broadcasts", "skipped_leads", server_default=None)


def downgrade() -> None:
    op.drop_column("broadcasts", "skipped_leads")
