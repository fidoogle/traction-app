"""add team memberships

People can now belong to several teams. Every existing user starts out as a
member of the team they were on (users.team_id, which stays as their home
team).

Revision ID: a7c3e91b2f04
Revises: e5a2c8f1b730
Create Date: 2026-10-09 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a7c3e91b2f04'
down_revision: Union[str, Sequence[str], None] = 'e5a2c8f1b730'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'team_memberships',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'team_id', name='uq_team_membership'),
    )
    op.create_index('ix_team_memberships_team_id', 'team_memberships', ['team_id'])
    op.execute(
        'INSERT INTO team_memberships (id, user_id, team_id) '
        'SELECT gen_random_uuid(), id, team_id FROM users'
    )


def downgrade() -> None:
    """Downgrade schema (extra memberships beyond each user's home team are lost)."""
    op.drop_index('ix_team_memberships_team_id', table_name='team_memberships')
    op.drop_table('team_memberships')
