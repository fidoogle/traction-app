import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import Date, DateTime, Enum as SAEnum, ForeignKey, SmallInteger
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin
from app.models.enums import MeetingStatus


class Meeting(UUIDPKMixin, Base):
    __tablename__ = "meetings"

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False
    )
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[MeetingStatus] = mapped_column(
        SAEnum(MeetingStatus, name="meeting_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=MeetingStatus.SCHEDULED,
    )

    team: Mapped["Team"] = relationship(back_populates="meetings")

    # Live-meeting bookkeeping (see app/core/meeting_session.py). The admin runs
    # the meeting's six timed steps from the sidebar; the time each step took
    # is kept here so the Meetings page can show it afterwards.
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Set by the final Stop: every counter is frozen until Finish.
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Furthest step reached (0-based); steps up to it can be (re)started.
    current_step: Mapped[Optional[int]] = mapped_column(SmallInteger)
    # The step whose clock is running, and since when (None when paused).
    running_step: Mapped[Optional[int]] = mapped_column(SmallInteger)
    running_since: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Whole seconds banked per step, not counting the running stretch.
    step_seconds: Mapped[List[int]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
