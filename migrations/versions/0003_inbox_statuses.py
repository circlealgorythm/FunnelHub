"""inbox statuses

Revision ID: 0003_inbox_statuses
Revises: 0002_bot_link_tokens
Create Date: 2026-06-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_inbox_statuses"
down_revision: str | None = "0002_bot_link_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_conversations_status", "conversations", type_="check")
    op.create_check_constraint(
        "ck_conversations_status",
        "conversations",
        "status IN ('open', 'pending', 'needs_reply', 'replied', 'closed')",
    )

    op.drop_constraint("ck_messages_status", "messages", type_="check")
    op.create_check_constraint(
        "ck_messages_status",
        "messages",
        "status IN ('created', 'queued', 'received', 'sent', 'delivered', 'read', 'failed')",
    )


def downgrade() -> None:
    op.execute("UPDATE conversations SET status = 'pending' WHERE status = 'needs_reply'")
    op.execute("UPDATE conversations SET status = 'open' WHERE status = 'replied'")
    op.execute("UPDATE messages SET status = 'created' WHERE status = 'received'")

    op.drop_constraint("ck_messages_status", "messages", type_="check")
    op.create_check_constraint(
        "ck_messages_status",
        "messages",
        "status IN ('created', 'queued', 'sent', 'delivered', 'read', 'failed')",
    )

    op.drop_constraint("ck_conversations_status", "conversations", type_="check")
    op.create_check_constraint(
        "ck_conversations_status",
        "conversations",
        "status IN ('open', 'pending', 'closed')",
    )
