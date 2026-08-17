import uuid
from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class PeopleAnalyzerEntryBase(BaseModel):
    user_id: uuid.UUID
    seat_id: uuid.UUID
    evaluated_at: date = Field(default_factory=date.today)
    gets_it: bool
    wants_it: bool
    has_capacity: bool
    core_values_ratings: dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None


class PeopleAnalyzerEntryCreate(PeopleAnalyzerEntryBase):
    pass


class PeopleAnalyzerEntryUpdate(BaseModel):
    user_id: Optional[uuid.UUID] = None
    seat_id: Optional[uuid.UUID] = None
    evaluated_at: Optional[date] = None
    gets_it: Optional[bool] = None
    wants_it: Optional[bool] = None
    has_capacity: Optional[bool] = None
    core_values_ratings: Optional[dict[str, Any]] = None
    notes: Optional[str] = None


class PeopleAnalyzerEntryRead(PeopleAnalyzerEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
