import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import GoalDirection, MeasurableUnit


class MeasurableBase(BaseModel):
    scorecard_id: uuid.UUID
    owner_id: Optional[uuid.UUID] = None
    name: str
    unit: MeasurableUnit = MeasurableUnit.NUMBER
    goal_value: float
    goal_direction: GoalDirection = GoalDirection.AT_LEAST
    position: int = 0


class MeasurableCreate(MeasurableBase):
    pass


class MeasurableUpdate(BaseModel):
    scorecard_id: Optional[uuid.UUID] = None
    owner_id: Optional[uuid.UUID] = None
    name: Optional[str] = None
    unit: Optional[MeasurableUnit] = None
    goal_value: Optional[float] = None
    goal_direction: Optional[GoalDirection] = None
    position: Optional[int] = None


class MeasurableRead(MeasurableBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
