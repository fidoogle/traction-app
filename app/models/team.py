import uuid
from typing import List, Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin


class Team(UUIDPKMixin, Base):
    __tablename__ = "teams"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    meeting_day: Mapped[Optional[str]] = mapped_column(String(20))

    organization: Mapped["Organization"] = relationship(back_populates="teams")
    users: Mapped[List["User"]] = relationship(
        back_populates="team", foreign_keys="User.team_id"
    )
    rocks: Mapped[List["Rock"]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )
    measurables: Mapped[List["Measurable"]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )
    issues: Mapped[List["Issue"]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )
    meetings: Mapped[List["Meeting"]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )
