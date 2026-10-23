import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Enum as SAEnum
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin
from app.models.enums import IssueStatus


class Issue(UUIDPKMixin, Base):
    __tablename__ = "issues"

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[IssueStatus] = mapped_column(
        SAEnum(IssueStatus, name="issue_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=IssueStatus.OPEN,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # When the team was emailed about this issue (the optional "new issue"
    # alert, which groups issues added close together). None = not yet.
    announced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    notes: Mapped[Optional[str]] = mapped_column(Text)

    team: Mapped["Team"] = relationship(back_populates="issues")
    todos: Mapped[List["Todo"]] = relationship(back_populates="issue")
