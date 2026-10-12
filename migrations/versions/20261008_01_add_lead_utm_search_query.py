"""Add search_query to lead_utm table.

Revision ID: 20261008_01
Revises: 20260908_01
Create Date: 2026-10-08
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261008_01"
down_revision: str | None = "20260908_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("lead_utm", sa.Column("search_query", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("lead_utm", "search_query")
