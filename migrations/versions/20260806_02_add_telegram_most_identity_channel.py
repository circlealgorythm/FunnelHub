"""Allow the isolated Most Telegram channel for messenger identities.

Revision ID: 20260806_02
Revises: 20260806_01
Create Date: 2026-08-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260806_02"
down_revision: str | None = "20260806_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_messenger_identities_channel", "messenger_identities", type_="check")
    op.create_check_constraint(
        "ck_messenger_identities_channel",
        "messenger_identities",
        "channel IN ('telegram', 'telegram_most', 'vk', 'max')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_messenger_identities_channel", "messenger_identities", type_="check")
    op.create_check_constraint(
        "ck_messenger_identities_channel",
        "messenger_identities",
        "channel IN ('telegram', 'vk', 'max')",
    )
