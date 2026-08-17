import uuid
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class VTOBase(BaseModel):
    core_values: list[Any] = Field(default_factory=list)
    core_focus_purpose: Optional[str] = None
    core_focus_niche: Optional[str] = None
    ten_year_target: Optional[dict[str, Any]] = None
    three_year_picture: Optional[dict[str, Any]] = None
    one_year_plan: Optional[dict[str, Any]] = None


class VTOUpsert(VTOBase):
    pass


class VTORead(VTOBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
