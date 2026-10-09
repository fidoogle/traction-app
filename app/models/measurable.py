import uuid
from typing import List, Optional

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin
from app.models.enums import GoalDirection, MeasurableUnit


class Measurable(UUIDPKMixin, Base):
    __tablename__ = "measurables"

    scorecard_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scorecards.id"), nullable=False
    )
    # Nullable so deleting a user leaves their rows (unowned) instead of failing.
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(
        String(10), nullable=False, default=MeasurableUnit.NUMBER.value
    )
    goal_value: Mapped[float] = mapped_column(Float, nullable=False)
    goal_direction: Mapped[str] = mapped_column(
        String(3), nullable=False, default=GoalDirection.AT_LEAST.value
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    scorecard: Mapped["Scorecard"] = relationship(back_populates="measurables")
    owner: Mapped[Optional["User"]] = relationship(foreign_keys=[owner_id])
    scorecard_entries: Mapped[List["ScorecardEntry"]] = relationship(
        back_populates="measurable", cascade="all, delete-orphan"
    )
