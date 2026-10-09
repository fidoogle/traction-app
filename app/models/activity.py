import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ActivityLog(Base):
    """One add/edit/delete of an EOS record, and who did it.

    Written automatically by the session hook in app.core.activity - routes
    don't create these themselves. Snapshots the actor's name and the
    record's label so entries still read correctly after either is deleted.
    """

    __tablename__ = "activity_log"
    __table_args__ = (Index("ix_activity_log_org_id_id", "org_id", "id"),)

    # Sequential (not UUID like the other tables) so newest-first ordering
    # and "show older" paging are just id comparisons - several entries
    # written in one transaction share the same created_at.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # The team the record belongs to; None for org-level changes (users, the
    # organization) - those are visible to admins only. See app.core.activity.
    team_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    actor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # "created" / "updated" / "deleted"
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    # Key into app.core.activity.ENTITY_TYPES, e.g. "rock", "todo".
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    entity_label: Mapped[str] = mapped_column(String(255), nullable=False)
    # Human-readable change lines for updates, e.g. ["Status: On Track -> Done"].
    changes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
