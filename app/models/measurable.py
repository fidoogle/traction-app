import uuid
from typing import List

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin


class Measurable(UUIDPKMixin, Base):
    __tablename__ = "measurables"

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    goal_value: Mapped[float] = mapped_column(Float, nullable=False)

    team: Mapped["Team"] = relationship(back_populates="measurables")
    scorecard_entries: Mapped[List["ScorecardEntry"]] = relationship(
        back_populates="measurable", cascade="all, delete-orphan"
    )
