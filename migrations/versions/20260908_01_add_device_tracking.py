"""Add hardware fingerprinting and real client IP tracking to leads.

Revision ID: 20260908_01
Revises: 20260821_01
Create Date: 2026-09-08
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260908_01"
down_revision: str | None = "20260821_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add columns to leads table
    op.add_column("leads", sa.Column("client_ip", sa.String(length=64), nullable=True))
    op.add_column("leads", sa.Column("device_fingerprint", sa.String(length=128), nullable=True))
    op.add_column("leads", sa.Column("device_gpu", sa.String(length=255), nullable=True))
    op.add_column("leads", sa.Column("device_screen", sa.String(length=64), nullable=True))
    op.add_column("leads", sa.Column("device_cpu_cores", sa.Integer(), nullable=True))
    op.add_column(
        "leads",
        sa.Column(
            "is_device_duplicate",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_leads_device_fingerprint"), "leads", ["device_fingerprint"], unique=False
    )

    # Add column to lead_utm table as well
    op.add_column("lead_utm", sa.Column("device_fingerprint", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("lead_utm", "device_fingerprint")
    op.drop_index(op.f("ix_leads_device_fingerprint"), table_name="leads")
    op.drop_column("leads", "is_device_duplicate")
    op.drop_column("leads", "device_cpu_cores")
    op.drop_column("leads", "device_screen")
    op.drop_column("leads", "device_gpu")
    op.drop_column("leads", "device_fingerprint")
    op.drop_column("leads", "client_ip")
