"""meeting session timers

A live meeting is run step by step from the sidebar; these columns keep the
state (so it survives reloads) and the time each step took.

Revision ID: a1d6c3e8b742
Revises: f3a9d1c7e5b2
Create Date: 2026-10-10 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1d6c3e8b742'
down_revision: Union[str, Sequence[str], None] = 'f3a9d1c7e5b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    for name in ('started_at', 'finished_at', 'stopped_at', 'running_since'):
        op.add_column('meetings', sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    op.add_column('meetings', sa.Column('current_step', sa.SmallInteger(), nullable=True))
    op.add_column('meetings', sa.Column('running_step', sa.SmallInteger(), nullable=True))
    op.add_column(
        'meetings',
        sa.Column('step_seconds', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    for name in ('step_seconds', 'running_step', 'current_step', 'running_since',
                 'stopped_at', 'finished_at', 'started_at'):
        op.drop_column('meetings', name)
