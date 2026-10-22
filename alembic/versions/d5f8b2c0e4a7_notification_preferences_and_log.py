"""notification preferences and log

Revision ID: d5f8b2c0e4a7
Revises: c4e7a1b9d3f6
Create Date: 2026-10-22 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd5f8b2c0e4a7'
down_revision: Union[str, Sequence[str], None] = 'c4e7a1b9d3f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'notification_preferences',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('key', sa.String(length=50), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'key', name='uq_notification_preference'),
    )
    op.create_table(
        'notification_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('key', sa.String(length=50), nullable=False),
        sa.Column('subject', sa.String(length=100), server_default='', nullable=False),
        sa.Column('period', sa.String(length=50), server_default='', nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('error', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'key', 'subject', 'period', name='uq_notification_log_once'),
    )
    op.create_index('ix_notification_log_created_at', 'notification_log', ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_notification_log_created_at', table_name='notification_log')
    op.drop_table('notification_log')
    op.drop_table('notification_preferences')
