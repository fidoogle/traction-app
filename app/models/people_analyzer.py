import uuid
from datetime import date
from typing import Any, Optional

from sqlalchemy import Boolean, Date, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin


class PeopleAnalyzerEntry(UUIDPKMixin, Base):
    """A single GWC (Get it / Want it / Capacity) + core values evaluation
    of a person in a specific seat, as of a point in time. Entries
    accumulate over time (re-evaluated periodically), unlike VTO which is
    a single current-state document.
    """

    __tablename__ = "people_analyzer_entries"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    seat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seats.id"), nullable=False
    )
    evaluated_at: Mapped[date] = mapped_column(Date, nullable=False)

    gets_it: Mapped[bool] = mapped_column(Boolean, nullable=False)
    wants_it: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_capacity: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # e.g. {"Integrity": true, "Ownership": false, ...}
    core_values_ratings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped["User"] = relationship(back_populates="people_analyzer_entries")
    seat: Mapped["Seat"] = relationship(back_populates="people_analyzer_entries")
