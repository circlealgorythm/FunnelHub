"""Keep project conversations separate for a shared lead.

Revision ID: 20260806_04
Revises: 20260806_03
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260806_04"
down_revision: str | None = "20260806_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("source", sa.String(length=64), nullable=True))
    op.create_index("ix_conversations_source", "conversations", ["source"])


def downgrade() -> None:
    op.drop_index("ix_conversations_source", table_name="conversations")
    op.drop_column("conversations", "source")
