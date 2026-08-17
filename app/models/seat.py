import uuid
from typing import List, Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin


class Seat(UUIDPKMixin, Base):
    __tablename__ = "seats"

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False
    )
    # Nullable: a seat can be vacant.
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    # Nullable, self-referencing: NULL means this seat is at the top of its
    # branch of the accountability chart. Deleting a parent seat detaches
    # (not deletes) its children rather than cascading the deletion down.
    parent_seat_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seats.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    responsibilities: Mapped[List[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )

    team: Mapped["Team"] = relationship(back_populates="seats")
    user: Mapped[Optional["User"]] = relationship(back_populates="seats")
    parent: Mapped[Optional["Seat"]] = relationship(
        remote_side="Seat.id", back_populates="children"
    )
    children: Mapped[List["Seat"]] = relationship(back_populates="parent")
    people_analyzer_entries: Mapped[List["PeopleAnalyzerEntry"]] = relationship(
        back_populates="seat", cascade="all, delete-orphan"
    )
