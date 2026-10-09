import uuid

from sqlalchemy import Boolean, ForeignKey, Index, UniqueConstraint, false, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin


class TeamMembership(UUIDPKMixin, Base):
    """A person belongs to one or more teams; this is one of those links.

    Role stays org-wide on User - an admin administers every team, whether
    or not they're a member of it. A member can also be made a *team admin*
    of one team (`is_team_admin`): admin-level rights on that team only.
    """

    __tablename__ = "team_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "team_id", name="uq_team_membership"),
        # A person is team admin of at most one team (a team can have several).
        Index(
            "uq_team_admin_one_team",
            "user_id",
            unique=True,
            postgresql_where=text("is_team_admin"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    is_team_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    user: Mapped["User"] = relationship(back_populates="memberships")
    team: Mapped["Team"] = relationship(back_populates="memberships")
