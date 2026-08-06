"""Allow the isolated Most Telegram channel for messages and conversations.

Revision ID: 20260806_03
Revises: 20260806_02
Create Date: 2026-08-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260806_03"
down_revision: str | None = "20260806_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def replace_channel_constraint(table_name: str, constraint_name: str, channels: str) -> None:
    op.drop_constraint(constraint_name, table_name, type_="check")
    op.create_check_constraint(constraint_name, table_name, f"channel IN ({channels})")


def upgrade() -> None:
    channels = "'telegram', 'telegram_most', 'vk', 'max', 'email'"
    replace_channel_constraint("conversations", "ck_conversations_channel", channels)
    replace_channel_constraint("messages", "ck_messages_channel", channels)


def downgrade() -> None:
    channels = "'telegram', 'vk', 'max', 'email'"
    replace_channel_constraint("conversations", "ck_conversations_channel", channels)
    replace_channel_constraint("messages", "ck_messages_channel", channels)
