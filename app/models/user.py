import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Enum as SAEnum
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin
from app.models.enums import UserRole


class User(UUIDPKMixin, Base):
    __tablename__ = "users"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    # Home team: the one shown first after login. Always also one of the
    # user's memberships (see TeamMembership), which are the teams they
    # can actually work in.
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    auth_provider: Mapped[Optional[str]] = mapped_column(String(50))
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=UserRole.MEMBER,
    )
    # Activity newer than this (by other people) counts as unread - drives
    # the badge on the sidebar's Activity link. Starts at account creation
    # so a new user isn't greeted by the whole backlog.
    activity_last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    organization: Mapped["Organization"] = relationship(back_populates="users")
    team: Mapped["Team"] = relationship(back_populates="users", foreign_keys=[team_id])
    memberships: Mapped[List["TeamMembership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    teams: Mapped[List["Team"]] = relationship(
        secondary="team_memberships", viewonly=True, order_by="Team.name"
    )
    rocks: Mapped[List["Rock"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    todos: Mapped[List["Todo"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    # No cascade: deleting a user should vacate their seat(s), not delete them.
    seats: Mapped[List["Seat"]] = relationship(back_populates="user")
    people_analyzer_entries: Mapped[List["PeopleAnalyzerEntry"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
