"""scorecards belong to a team

Each scorecard now belongs to one team. Existing scorecards go to the team
most of their measurable owners are on (by home team), or - with no owned
rows - the org's first team by name.

Revision ID: c2d8f4a6e913
Revises: a7c3e91b2f04
Create Date: 2026-10-09 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c2d8f4a6e913'
down_revision: Union[str, Sequence[str], None] = 'a7c3e91b2f04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('scorecards', sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(
        """
        UPDATE scorecards s SET team_id = COALESCE(
            (SELECT u.team_id
               FROM measurables m JOIN users u ON u.id = m.owner_id
              WHERE m.scorecard_id = s.id
              GROUP BY u.team_id
              ORDER BY count(*) DESC, u.team_id
              LIMIT 1),
            (SELECT t.id FROM teams t WHERE t.org_id = s.org_id ORDER BY t.name, t.id LIMIT 1)
        )
        """
    )
    op.alter_column('scorecards', 'team_id', nullable=False)
    op.create_foreign_key('scorecards_team_id_fkey', 'scorecards', 'teams', ['team_id'], ['id'])
    op.create_index('ix_scorecards_team_id', 'scorecards', ['team_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_scorecards_team_id', table_name='scorecards')
    op.drop_constraint('scorecards_team_id_fkey', 'scorecards', type_='foreignkey')
    op.drop_column('scorecards', 'team_id')
