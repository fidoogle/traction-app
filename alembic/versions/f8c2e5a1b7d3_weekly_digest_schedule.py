"""weekly digest schedule on organizations

Revision ID: f8c2e5a1b7d3
Revises: e6a9c3d1f8b4
Create Date: 2026-10-23 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f8c2e5a1b7d3'
down_revision: Union[str, Sequence[str], None] = 'e6a9c3d1f8b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('organizations', sa.Column('digest_weekday', sa.SmallInteger(), server_default='0', nullable=False))
    op.add_column('organizations', sa.Column('digest_time', sa.Time(), server_default='07:00:00', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('organizations', 'digest_time')
    op.drop_column('organizations', 'digest_weekday')
