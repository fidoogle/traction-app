"""team admin flag on team memberships

A member can be made admin of one team: `team_memberships.is_team_admin`.
The partial unique index keeps a person to one such team.

Revision ID: b6d2f8a3c1e7
Revises: a1d6c3e8b742
Create Date: 2026-10-09 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b6d2f8a3c1e7'
down_revision: Union[str, Sequence[str], None] = 'a1d6c3e8b742'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'team_memberships',
        sa.Column('is_team_admin', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        'uq_team_admin_one_team',
        'team_memberships',
        ['user_id'],
        unique=True,
        postgresql_where=sa.text('is_team_admin'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_team_admin_one_team', table_name='team_memberships')
    op.drop_column('team_memberships', 'is_team_admin')
