import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import MeetingStatus


class MeetingBase(BaseModel):
    team_id: uuid.UUID
    scheduled_start: datetime
    duration_minutes: int = 90
    location: Optional[str] = None
    status: MeetingStatus = MeetingStatus.SCHEDULED


class MeetingCreate(MeetingBase):
    pass


class MeetingUpdate(BaseModel):
    team_id: Optional[uuid.UUID] = None
    scheduled_start: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    location: Optional[str] = None
    status: Optional[MeetingStatus] = None


class MeetingRead(MeetingBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
