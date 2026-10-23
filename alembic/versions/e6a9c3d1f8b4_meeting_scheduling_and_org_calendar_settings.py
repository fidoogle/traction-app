"""meeting scheduling, org time zone / calendar settings, calendar feed token

meetings.scheduled_date (a date) becomes scheduled_start (a moment), plus a
length, a location and the calendar identity (uid + sequence).

Existing meetings that were actually run keep the moment they started. The
rest (scheduled, never started) get 9:00 AM US Central on their date.

Revision ID: e6a9c3d1f8b4
Revises: d5f8b2c0e4a7
Create Date: 2026-10-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e6a9c3d1f8b4'
down_revision: Union[str, Sequence[str], None] = 'd5f8b2c0e4a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('meetings', sa.Column('scheduled_start', sa.DateTime(timezone=True), nullable=True))
    op.add_column('meetings', sa.Column('duration_minutes', sa.Integer(), server_default='90', nullable=False))
    op.add_column('meetings', sa.Column('location', sa.String(length=255), nullable=True))
    op.add_column('meetings', sa.Column('ical_uid', sa.String(length=64), nullable=True))
    op.add_column('meetings', sa.Column('ical_sequence', sa.Integer(), server_default='0', nullable=False))

    op.execute(
        "UPDATE meetings SET "
        "scheduled_start = COALESCE(started_at, (scheduled_date + time '09:00') AT TIME ZONE 'America/Chicago'), "
        "ical_uid = gen_random_uuid()::text"
    )
    op.alter_column('meetings', 'scheduled_start', nullable=False)
    op.alter_column('meetings', 'ical_uid', nullable=False)
    op.create_unique_constraint('uq_meetings_ical_uid', 'meetings', ['ical_uid'])
    op.drop_column('meetings', 'scheduled_date')

    op.add_column(
        'organizations',
        sa.Column('timezone', sa.String(length=64), server_default='America/Chicago', nullable=False),
    )
    op.add_column(
        'organizations',
        sa.Column('calendar_web_links', sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    op.add_column('users', sa.Column('calendar_token', sa.String(length=64), nullable=True))
    op.create_unique_constraint('uq_users_calendar_token', 'users', ['calendar_token'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_users_calendar_token', 'users', type_='unique')
    op.drop_column('users', 'calendar_token')

    op.drop_column('organizations', 'calendar_web_links')
    op.drop_column('organizations', 'timezone')

    op.add_column('meetings', sa.Column('scheduled_date', sa.Date(), nullable=True))
    op.execute(
        "UPDATE meetings SET scheduled_date = (scheduled_start AT TIME ZONE 'America/Chicago')::date"
    )
    op.alter_column('meetings', 'scheduled_date', nullable=False)
    op.drop_constraint('uq_meetings_ical_uid', 'meetings', type_='unique')
    op.drop_column('meetings', 'ical_sequence')
    op.drop_column('meetings', 'ical_uid')
    op.drop_column('meetings', 'location')
    op.drop_column('meetings', 'duration_minutes')
    op.drop_column('meetings', 'scheduled_start')
