"""add user role

Revision ID: 80d26fb29ca2
Revises: 52c178cbee2c
Create Date: 2026-08-17 13:18:32.199828

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '80d26fb29ca2'
down_revision: Union[str, Sequence[str], None] = '52c178cbee2c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

user_role_enum = postgresql.ENUM('admin', 'member', 'viewer', name='user_role')


def upgrade() -> None:
    """Upgrade schema."""
    # Postgres does not auto-create enum types for ADD COLUMN the way it
    # does for CREATE TABLE, so the type has to be created explicitly first.
    user_role_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'users',
        sa.Column(
            'role',
            user_role_enum,
            nullable=False,
            server_default='member',
        ),
    )
    # Server default only exists to backfill any pre-existing rows; new rows
    # should rely on the application-level default instead.
    op.alter_column('users', 'role', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'role')
    user_role_enum.drop(op.get_bind(), checkfirst=True)
