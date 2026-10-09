import uuid
from datetime import date, timedelta
from typing import List

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin

SCORECARD_WEEKS = 13


class Scorecard(UUIDPKMixin, Base):
    """A 13-week scorecard. Each week is 7 days, week 1 beginning on start_date."""

    __tablename__ = "scorecards"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)

    team: Mapped["Team"] = relationship(back_populates="scorecards")
    measurables: Mapped[List["Measurable"]] = relationship(
        back_populates="scorecard",
        cascade="all, delete-orphan",
        order_by="Measurable.position, Measurable.name",
    )

    def week_start(self, week: int) -> date:
        return self.start_date + timedelta(weeks=week - 1)

    @property
    def end_date(self) -> date:
        return self.week_start(SCORECARD_WEEKS) + timedelta(days=6)
