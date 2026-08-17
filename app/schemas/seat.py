import uuid
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SeatBase(BaseModel):
    team_id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    parent_seat_id: Optional[uuid.UUID] = None
    title: str
    responsibilities: List[str] = Field(default_factory=list)


class SeatCreate(SeatBase):
    pass


class SeatUpdate(BaseModel):
    team_id: Optional[uuid.UUID] = None
    user_id: Optional[uuid.UUID] = None
    parent_seat_id: Optional[uuid.UUID] = None
    title: Optional[str] = None
    responsibilities: Optional[List[str]] = None


class SeatRead(SeatBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
