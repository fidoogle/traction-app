"""todos belong to a team

Each to-do now belongs to one team. Existing to-dos go to their related
issue's team, or - with no issue - their owner's home team.

Revision ID: d9e5b7a1c4f2
Revises: c2d8f4a6e913
Create Date: 2026-10-09 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd9e5b7a1c4f2'
down_revision: Union[str, Sequence[str], None] = 'c2d8f4a6e913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('todos', sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(
        """
        UPDATE todos t SET team_id = COALESCE(
            (SELECT i.team_id FROM issues i WHERE i.id = t.issue_id),
            (SELECT u.team_id FROM users u WHERE u.id = t.owner_id)
        )
        """
    )
    op.alter_column('todos', 'team_id', nullable=False)
    op.create_foreign_key('todos_team_id_fkey', 'todos', 'teams', ['team_id'], ['id'])
    op.create_index('ix_todos_team_id', 'todos', ['team_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_todos_team_id', table_name='todos')
    op.drop_constraint('todos_team_id_fkey', 'todos', type_='foreignkey')
    op.drop_column('todos', 'team_id')
