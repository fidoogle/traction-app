import uuid
from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import TodoStatus


class TodoBase(BaseModel):
    owner_id: uuid.UUID
    issue_id: Optional[uuid.UUID] = None
    title: str
    due_date: Optional[date] = None
    status: TodoStatus = TodoStatus.OPEN


class TodoCreate(TodoBase):
    pass


class TodoUpdate(BaseModel):
    owner_id: Optional[uuid.UUID] = None
    issue_id: Optional[uuid.UUID] = None
    title: Optional[str] = None
    due_date: Optional[date] = None
    status: Optional[TodoStatus] = None


class TodoRead(TodoBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
