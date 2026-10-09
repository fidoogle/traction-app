import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin


class ScorecardEntry(UUIDPKMixin, Base):
    """One cell of a scorecard. A blank cell is simply the absence of a row."""

    __tablename__ = "scorecard_entries"
    __table_args__ = (
        UniqueConstraint(
            "measurable_id", "week_number", name="uq_scorecard_entry_measurable_week"
        ),
        CheckConstraint("week_number BETWEEN 1 AND 13", name="ck_scorecard_entry_week"),
    )

    measurable_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("measurables.id"), nullable=False
    )
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_value: Mapped[float] = mapped_column(Float, nullable=False)

    measurable: Mapped["Measurable"] = relationship(back_populates="scorecard_entries")
