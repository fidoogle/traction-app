"""scorecards and weekly grid

Replaces the per-team measurable cards with 13-week scorecards. Existing
measurables and entries are deleted (agreed: the old data is not carried over).

Revision ID: e5a2c8f1b730
Revises: d41e7a9c5b20
Create Date: 2026-10-09 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e5a2c8f1b730'
down_revision: Union[str, Sequence[str], None] = 'd41e7a9c5b20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute('DELETE FROM scorecard_entries')
    op.execute('DELETE FROM measurables')

    op.create_table(
        'scorecards',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.drop_column('measurables', 'team_id')
    op.add_column('measurables', sa.Column('scorecard_id', postgresql.UUID(as_uuid=True), nullable=False))
    op.add_column('measurables', sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('measurables', sa.Column('unit', sa.String(length=10), nullable=False))
    op.add_column('measurables', sa.Column('goal_direction', sa.String(length=3), nullable=False))
    op.add_column('measurables', sa.Column('position', sa.Integer(), nullable=False))
    op.create_foreign_key('measurables_scorecard_id_fkey', 'measurables', 'scorecards', ['scorecard_id'], ['id'])
    op.create_foreign_key('measurables_owner_id_fkey', 'measurables', 'users', ['owner_id'], ['id'], ondelete='SET NULL')

    op.drop_constraint('uq_scorecard_entry_measurable_week', 'scorecard_entries', type_='unique')
    op.drop_column('scorecard_entries', 'week_ending')
    op.add_column('scorecard_entries', sa.Column('week_number', sa.Integer(), nullable=False))
    op.create_unique_constraint('uq_scorecard_entry_measurable_week', 'scorecard_entries', ['measurable_id', 'week_number'])
    op.create_check_constraint('ck_scorecard_entry_week', 'scorecard_entries', 'week_number BETWEEN 1 AND 13')


def downgrade() -> None:
    """Downgrade schema (scorecard data is discarded)."""
    op.execute('DELETE FROM scorecard_entries')
    op.execute('DELETE FROM measurables')

    op.drop_constraint('ck_scorecard_entry_week', 'scorecard_entries', type_='check')
    op.drop_constraint('uq_scorecard_entry_measurable_week', 'scorecard_entries', type_='unique')
    op.drop_column('scorecard_entries', 'week_number')
    op.add_column('scorecard_entries', sa.Column('week_ending', sa.Date(), nullable=False))
    op.create_unique_constraint('uq_scorecard_entry_measurable_week', 'scorecard_entries', ['measurable_id', 'week_ending'])

    op.drop_constraint('measurables_owner_id_fkey', 'measurables', type_='foreignkey')
    op.drop_constraint('measurables_scorecard_id_fkey', 'measurables', type_='foreignkey')
    op.drop_column('measurables', 'position')
    op.drop_column('measurables', 'goal_direction')
    op.drop_column('measurables', 'unit')
    op.drop_column('measurables', 'owner_id')
    op.drop_column('measurables', 'scorecard_id')
    op.add_column('measurables', sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=False))
    op.create_foreign_key('measurables_team_id_fkey', 'measurables', 'teams', ['team_id'], ['id'])
    op.drop_table('scorecards')
