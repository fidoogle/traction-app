import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import IssueStatus


class IssueBase(BaseModel):
    team_id: uuid.UUID
    title: str
    status: IssueStatus = IssueStatus.OPEN
    priority: int = 0


class IssueCreate(IssueBase):
    pass


class IssueUpdate(BaseModel):
    team_id: Optional[uuid.UUID] = None
    title: Optional[str] = None
    status: Optional[IssueStatus] = None
    priority: Optional[int] = None


class IssueRead(IssueBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
