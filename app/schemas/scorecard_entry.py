import uuid
from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ScorecardEntryBase(BaseModel):
    measurable_id: uuid.UUID
    week_ending: date
    actual_value: float


class ScorecardEntryCreate(ScorecardEntryBase):
    pass


class ScorecardEntryUpdate(BaseModel):
    measurable_id: Optional[uuid.UUID] = None
    week_ending: Optional[date] = None
    actual_value: Optional[float] = None


class ScorecardEntryRead(ScorecardEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
