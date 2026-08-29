"""Add Yandex attribution identifiers to lead UTM snapshots.

Revision ID: 20260821_01
Revises: 20260806_05
Create Date: 2026-08-21
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_01"
down_revision: str | None = "20260806_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("lead_utm", sa.Column("yclid", sa.String(length=255), nullable=True))
    op.add_column("lead_utm", sa.Column("metrika_client_id", sa.String(length=255), nullable=True))
    op.add_column("lead_utm", sa.Column("metrika_visit_id", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("lead_utm", "metrika_visit_id")
    op.drop_column("lead_utm", "metrika_client_id")
    op.drop_column("lead_utm", "yclid")
