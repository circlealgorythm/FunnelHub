"""add channel to funnelstate

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-06 14:08:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add column with a default
    op.add_column('funnel_states', sa.Column('channel', sa.String(length=32), nullable=False, server_default='unknown'))
    
    # 2. Backfill existing data using metadata_->>'messenger_channel' or 'email'
    op.execute("""
        UPDATE funnel_states
        SET channel = COALESCE(
            metadata->>'messenger_channel',
            CASE WHEN funnel_key = 'aisu_email_sequence' THEN 'email' ELSE 'unknown' END
        )
    """)
    
    # 3. Drop old constraint and create new one
    op.drop_constraint('funnel_states_lead_id_funnel_key_key', 'funnel_states', type_='unique')
    op.create_unique_constraint('funnel_states_lead_id_funnel_key_channel_key', 'funnel_states', ['lead_id', 'funnel_key', 'channel'])


def downgrade() -> None:
    # 1. Revert constraint
    op.drop_constraint('funnel_states_lead_id_funnel_key_channel_key', 'funnel_states', type_='unique')
    op.create_unique_constraint('funnel_states_lead_id_funnel_key_key', 'funnel_states', ['lead_id', 'funnel_key'])
    
    # 2. Drop column
    op.drop_column('funnel_states', 'channel')
