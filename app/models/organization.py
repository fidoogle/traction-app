from datetime import time
from typing import List, Optional

from sqlalchemy import Boolean, SmallInteger, String, Time, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin


class Organization(UUIDPKMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    logo_url: Mapped[Optional[str]] = mapped_column(String(1024))
    # Meeting times are typed and shown in this zone (an IANA name, so daylight
    # saving is handled).
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="America/Chicago", server_default="America/Chicago"
    )
    # When the weekly summary email goes out, by the organization's clock:
    # 0 = Monday ... 6 = Sunday, at this time of day. One schedule for everyone.
    digest_weekday: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
    digest_time: Mapped[time] = mapped_column(
        Time, nullable=False, default=time(7, 0), server_default="07:00:00"
    )
    # Whether invitation emails also carry "Add to Google / Outlook" links.
    # Those point at outside sites, so they are off unless an admin turns them on.
    calendar_web_links: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    teams: Mapped[List["Team"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    users: Mapped[List["User"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    scorecards: Mapped[List["Scorecard"]] = relationship(
        cascade="all, delete-orphan", order_by="Scorecard.start_date.desc()"
    )
    vtos: Mapped[List["VTO"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
