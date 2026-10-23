"""issues: created_at and announced_at (for the grouped new-issue alert)

Issues that exist before this migration count as already announced, so turning
the alert on never emails about old issues.

Revision ID: a9d3f6b2c8e1
Revises: f8c2e5a1b7d3
Create Date: 2026-10-23 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a9d3f6b2c8e1'
down_revision: Union[str, Sequence[str], None] = 'f8c2e5a1b7d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('issues', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('issues', sa.Column('announced_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE issues SET announced_at = now()")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('issues', 'announced_at')
    op.drop_column('issues', 'created_at')
