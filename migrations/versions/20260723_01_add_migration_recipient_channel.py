"""Add channel support to legacy migration recipients.

Revision ID: 20260723_01
Revises: 20260720_01
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_01"
down_revision: str | None = "20260720_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "legacy_telegram_migration_recipients",
        sa.Column("channel", sa.String(length=32), nullable=False, server_default="telegram"),
    )
    op.alter_column(
        "legacy_telegram_migration_recipients",
        "bot_link_token_id",
        existing_type=sa.UUID(),
        nullable=True,
    )
    op.alter_column(
        "legacy_telegram_migration_recipients",
        "telegram_identity_id",
        new_column_name="messenger_identity_id",
        existing_type=sa.UUID(),
        existing_nullable=True,
    )
    op.create_index(
        "ix_legacy_migration_recipient_channel",
        "legacy_telegram_migration_recipients",
        ["campaign_id", "channel"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_legacy_migration_recipient_channel",
        table_name="legacy_telegram_migration_recipients",
    )
    op.alter_column(
        "legacy_telegram_migration_recipients",
        "messenger_identity_id",
        new_column_name="telegram_identity_id",
        existing_type=sa.UUID(),
        existing_nullable=True,
    )
    op.alter_column(
        "legacy_telegram_migration_recipients",
        "bot_link_token_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
    op.drop_column("legacy_telegram_migration_recipients", "channel")
