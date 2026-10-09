import uuid
from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ScorecardBase(BaseModel):
    org_id: uuid.UUID
    name: str
    start_date: date


class ScorecardCreate(ScorecardBase):
    pass


class ScorecardUpdate(BaseModel):
    org_id: Optional[uuid.UUID] = None
    name: Optional[str] = None
    start_date: Optional[date] = None


class ScorecardRead(ScorecardBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
