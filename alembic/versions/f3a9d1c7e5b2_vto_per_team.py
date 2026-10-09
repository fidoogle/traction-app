"""one VTO per team

The Vision/Traction Organizer belongs to a team instead of the whole org.
An org's existing VTO goes to its first team by name; the other teams start
blank. Activity entries about a VTO are matched up to its team too.

Revision ID: f3a9d1c7e5b2
Revises: e8b2c6d4a1f9
Create Date: 2026-10-09 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f3a9d1c7e5b2'
down_revision: Union[str, Sequence[str], None] = 'e8b2c6d4a1f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('vtos', sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(
        """
        UPDATE vtos v SET team_id = (
            SELECT t.id FROM teams t WHERE t.org_id = v.org_id ORDER BY t.name, t.id LIMIT 1
        )
        """
    )
    # An org with a VTO but no team can't exist in practice; drop it rather than fail.
    op.execute('DELETE FROM vtos WHERE team_id IS NULL')
    op.alter_column('vtos', 'team_id', nullable=False)
    op.create_foreign_key('vtos_team_id_fkey', 'vtos', 'teams', ['team_id'], ['id'])
    op.create_unique_constraint('vtos_team_id_key', 'vtos', ['team_id'])
    op.drop_constraint('vtos_org_id_key', 'vtos', type_='unique')
    op.execute(
        "UPDATE activity_log a SET team_id = v.team_id FROM vtos v "
        "WHERE a.entity_type = 'vto' AND a.entity_id = v.id"
    )


def downgrade() -> None:
    """Downgrade schema (an org keeps only one of its teams' VTOs)."""
    op.execute(
        'DELETE FROM vtos v USING vtos w WHERE v.org_id = w.org_id AND v.id::text > w.id::text'
    )
    op.create_unique_constraint('vtos_org_id_key', 'vtos', ['org_id'])
    op.drop_constraint('vtos_team_id_key', 'vtos', type_='unique')
    op.drop_constraint('vtos_team_id_fkey', 'vtos', type_='foreignkey')
    op.drop_column('vtos', 'team_id')
