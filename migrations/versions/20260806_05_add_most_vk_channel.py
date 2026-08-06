"""Add the dedicated VK channel for Most tsennostey.

Revision ID: 20260806_05
Revises: 20260806_04
Create Date: 2026-08-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260806_05"
down_revision: str | None = "20260806_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_messenger_identities_channel", "messenger_identities", type_="check")
    op.create_check_constraint(
        "ck_messenger_identities_channel",
        "messenger_identities",
        "channel IN ('telegram', 'telegram_most', 'vk', 'vk_most', 'max')",
    )
    for table_name, constraint_name in (
        ("conversations", "ck_conversations_channel"),
        ("messages", "ck_messages_channel"),
    ):
        op.drop_constraint(constraint_name, table_name, type_="check")
        op.create_check_constraint(
            constraint_name,
            table_name,
            "channel IN ('telegram', 'telegram_most', 'vk', 'vk_most', 'max', 'email')",
        )


def downgrade() -> None:
    op.drop_constraint("ck_messenger_identities_channel", "messenger_identities", type_="check")
    op.create_check_constraint(
        "ck_messenger_identities_channel",
        "messenger_identities",
        "channel IN ('telegram', 'telegram_most', 'vk', 'max')",
    )
    for table_name, constraint_name in (
        ("conversations", "ck_conversations_channel"),
        ("messages", "ck_messages_channel"),
    ):
        op.drop_constraint(constraint_name, table_name, type_="check")
        op.create_check_constraint(
            constraint_name,
            table_name,
            "channel IN ('telegram', 'telegram_most', 'vk', 'max', 'email')",
        )
