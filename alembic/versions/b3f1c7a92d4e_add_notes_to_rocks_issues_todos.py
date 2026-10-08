"""add notes to rocks, issues, todos

Revision ID: b3f1c7a92d4e
Revises: 628615f6a962
Create Date: 2026-10-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b3f1c7a92d4e'
down_revision: Union[str, Sequence[str], None] = '628615f6a962'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('rocks', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('issues', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('todos', sa.Column('notes', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('todos', 'notes')
    op.drop_column('issues', 'notes')
    op.drop_column('rocks', 'notes')
