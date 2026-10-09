"""activity log entries know their team

So the Activity feed and its unread badge can follow the current team.
Entries are stamped with the team of the record they're about; existing
entries are matched up from the records that still exist. Entries with no
team (user/org changes, deleted records from before this) stay visible to
admins only.

Revision ID: e8b2c6d4a1f9
Revises: d9e5b7a1c4f2
Create Date: 2026-10-09 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e8b2c6d4a1f9'
down_revision: Union[str, Sequence[str], None] = 'd9e5b7a1c4f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# entity_type -> SQL that yields (entity_id, team_id) for existing records.
_BACKFILL = {
    'rock': 'SELECT id, team_id FROM rocks',
    'issue': 'SELECT id, team_id FROM issues',
    'todo': 'SELECT id, team_id FROM todos',
    'meeting': 'SELECT id, team_id FROM meetings',
    'seat': 'SELECT id, team_id FROM seats',
    'scorecard': 'SELECT id, team_id FROM scorecards',
    'team': 'SELECT id, id FROM teams',
    'team_membership': 'SELECT id, team_id FROM team_memberships',
    'measurable': (
        'SELECT m.id, s.team_id FROM measurables m JOIN scorecards s ON s.id = m.scorecard_id'
    ),
    'scorecard_entry': (
        'SELECT e.id, s.team_id FROM scorecard_entries e '
        'JOIN measurables m ON m.id = e.measurable_id '
        'JOIN scorecards s ON s.id = m.scorecard_id'
    ),
    'people_analyzer_entry': (
        'SELECT p.id, s.team_id FROM people_analyzer_entries p JOIN seats s ON s.id = p.seat_id'
    ),
}


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('activity_log', sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'activity_log_team_id_fkey', 'activity_log', 'teams', ['team_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_activity_log_team_id', 'activity_log', ['team_id'])
    for entity_type, source in _BACKFILL.items():
        op.execute(
            f"UPDATE activity_log a SET team_id = src.team_id "
            f"FROM ({source}) AS src(id, team_id) "
            f"WHERE a.entity_type = '{entity_type}' AND a.entity_id = src.id"
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_activity_log_team_id', table_name='activity_log')
    op.drop_constraint('activity_log_team_id_fkey', 'activity_log', type_='foreignkey')
    op.drop_column('activity_log', 'team_id')
