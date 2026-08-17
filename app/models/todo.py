import uuid
from datetime import date
from typing import Optional

from sqlalchemy import Date, Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin
from app.models.enums import TodoStatus


class Todo(UUIDPKMixin, Base):
    __tablename__ = "todos"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    # Nullable: to-dos commonly come straight out of an L10 meeting, not
    # only from an issue that was IDS'd.
    issue_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issues.id")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    status: Mapped[TodoStatus] = mapped_column(
        SAEnum(TodoStatus, name="todo_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=TodoStatus.OPEN,
    )

    owner: Mapped["User"] = relationship(back_populates="todos")
    issue: Mapped[Optional["Issue"]] = relationship(back_populates="todos")
