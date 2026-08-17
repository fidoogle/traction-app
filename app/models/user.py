import uuid
from typing import List, Optional

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin
from app.models.enums import UserRole


class User(UUIDPKMixin, Base):
    __tablename__ = "users"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
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

    organization: Mapped["Organization"] = relationship(back_populates="users")
    team: Mapped["Team"] = relationship(back_populates="users", foreign_keys=[team_id])
    rocks: Mapped[List["Rock"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    todos: Mapped[List["Todo"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
