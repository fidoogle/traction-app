import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin


class NotificationPreference(UUIDPKMixin, Base):
    """A person's own choice for one kind of email, overriding the default.
    Only choices that differ from the default are kept (see
    app/core/notifications.py), so changing a default later reaches everyone
    who hasn't chosen."""

    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_notification_preference"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)


class NotificationLog(UUIDPKMixin, Base):
    """One row per email attempted through notify(). The unique key is what
    stops the same notice going out twice (a restarted worker, a retried
    request): `subject` names the thing it is about ("todo:<id>") and `period`
    the occasion ("2026-W43", a meeting's sequence number), both "" if unused."""

    __tablename__ = "notification_log"
    __table_args__ = (
        UniqueConstraint("user_id", "key", "subject", "period", name="uq_notification_log_once"),
        Index("ix_notification_log_created_at", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(50), nullable=False)
    subject: Mapped[str] = mapped_column(String(100), nullable=False, default="", server_default="")
    period: Mapped[str] = mapped_column(String(50), nullable=False, default="", server_default="")
    # "pending" while being sent, then "sent" or "failed".
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    error: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
