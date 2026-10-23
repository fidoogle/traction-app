"""todos: created_at (so a meeting recap can list the To-Dos made during it)

Revision ID: b1e4a7c9d2f5
Revises: a9d3f6b2c8e1
Create Date: 2026-10-23 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b1e4a7c9d2f5'
down_revision: Union[str, Sequence[str], None] = 'a9d3f6b2c8e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('todos', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('todos', 'created_at')
