import uuid
from typing import Any, List, Optional

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin


class VTO(UUIDPKMixin, Base):
    """Vision/Traction Organizer: one current-state document per org.

    Core values and the longer-range sections vary too much org to org to
    force into rigid columns, so they're stored as JSONB rather than
    normalized tables - the org edits this in place as their plan evolves.
    """

    __tablename__ = "vtos"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, unique=True
    )

    # e.g. [{"name": "Integrity", "description": "..."}, ...]
    core_values: Mapped[List[Any]] = mapped_column(JSONB, nullable=False, default=list)

    core_focus_purpose: Mapped[Optional[str]] = mapped_column(Text)
    core_focus_niche: Mapped[Optional[str]] = mapped_column(Text)

    # e.g. {"description": "...", "target_date": "2036-06-30"}
    ten_year_target: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    # e.g. {"target_date": "...", "looks_like": ["...", "..."], ...}
    three_year_picture: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    # e.g. {"target_date": "...", "goals": ["...", "..."], ...}
    one_year_plan: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)

    organization: Mapped["Organization"] = relationship(back_populates="vto")
