import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TeamBase(BaseModel):
    org_id: uuid.UUID
    name: str
    meeting_day: Optional[str] = None


class TeamCreate(TeamBase):
    pass


class TeamUpdate(BaseModel):
    org_id: Optional[uuid.UUID] = None
    name: Optional[str] = None
    meeting_day: Optional[str] = None


class TeamRead(TeamBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
