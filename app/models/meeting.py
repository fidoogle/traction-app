import uuid
from datetime import date

from sqlalchemy import Date, Enum as SAEnum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
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
