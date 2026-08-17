import uuid
from datetime import date

from sqlalchemy import Date, Float, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin


class ScorecardEntry(UUIDPKMixin, Base):
    __tablename__ = "scorecard_entries"
    __table_args__ = (
        UniqueConstraint(
            "measurable_id", "week_ending", name="uq_scorecard_entry_measurable_week"
        ),
    )

    measurable_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("measurables.id"), nullable=False
    )
    week_ending: Mapped[date] = mapped_column(Date, nullable=False)
    actual_value: Mapped[float] = mapped_column(Float, nullable=False)

    measurable: Mapped["Measurable"] = relationship(back_populates="scorecard_entries")
