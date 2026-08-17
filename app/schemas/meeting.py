import uuid
from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import MeetingStatus


class MeetingBase(BaseModel):
    team_id: uuid.UUID
    scheduled_date: date
    status: MeetingStatus = MeetingStatus.SCHEDULED


class MeetingCreate(MeetingBase):
    pass


class MeetingUpdate(BaseModel):
    team_id: Optional[uuid.UUID] = None
    scheduled_date: Optional[date] = None
    status: Optional[MeetingStatus] = None


class MeetingRead(MeetingBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
