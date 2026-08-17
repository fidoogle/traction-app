import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import RockStatus


class RockBase(BaseModel):
    team_id: uuid.UUID
    owner_id: uuid.UUID
    title: str
    quarter: str
    status: RockStatus = RockStatus.ON_TRACK


class RockCreate(RockBase):
    pass


class RockUpdate(BaseModel):
    team_id: Optional[uuid.UUID] = None
    owner_id: Optional[uuid.UUID] = None
    title: Optional[str] = None
    quarter: Optional[str] = None
    status: Optional[RockStatus] = None


class RockRead(RockBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
