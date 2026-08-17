import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin
from app.models.enums import RockStatus


class Rock(UUIDPKMixin, Base):
    __tablename__ = "rocks"

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    quarter: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[RockStatus] = mapped_column(
        SAEnum(RockStatus, name="rock_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=RockStatus.ON_TRACK,
    )

    team: Mapped["Team"] = relationship(back_populates="rocks")
    owner: Mapped["User"] = relationship(back_populates="rocks")
