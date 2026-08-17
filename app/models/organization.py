from typing import List, Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin


class Organization(UUIDPKMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    logo_url: Mapped[Optional[str]] = mapped_column(String(1024))

    teams: Mapped[List["Team"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    users: Mapped[List["User"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    vto: Mapped[Optional["VTO"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan", uselist=False
    )
