import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin


class TeamMembership(UUIDPKMixin, Base):
    """A person belongs to one or more teams; this is one of those links.

    Role stays org-wide on User - an admin administers every team, whether
    or not they're a member of it.
    """

    __tablename__ = "team_memberships"
    __table_args__ = (UniqueConstraint("user_id", "team_id", name="uq_team_membership"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="memberships")
    team: Mapped["Team"] = relationship(back_populates="memberships")
