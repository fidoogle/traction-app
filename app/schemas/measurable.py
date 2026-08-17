import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict


class MeasurableBase(BaseModel):
    team_id: uuid.UUID
    name: str
    goal_value: float


class MeasurableCreate(MeasurableBase):
    pass


class MeasurableUpdate(BaseModel):
    team_id: Optional[uuid.UUID] = None
    name: Optional[str] = None
    goal_value: Optional[float] = None


class MeasurableRead(MeasurableBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
