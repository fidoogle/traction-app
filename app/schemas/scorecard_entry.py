import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ScorecardEntryBase(BaseModel):
    measurable_id: uuid.UUID
    week_number: int = Field(ge=1, le=13)
    actual_value: float


class ScorecardEntryCreate(ScorecardEntryBase):
    pass


class ScorecardEntryUpdate(BaseModel):
    measurable_id: Optional[uuid.UUID] = None
    week_number: Optional[int] = Field(default=None, ge=1, le=13)
    actual_value: Optional[float] = None


class ScorecardEntryRead(ScorecardEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
