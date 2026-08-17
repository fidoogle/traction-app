import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr


class UserBase(BaseModel):
    org_id: uuid.UUID
    team_id: uuid.UUID
    name: str
    email: EmailStr
    auth_provider: Optional[str] = None


class UserCreate(UserBase):
    pass


class UserUpdate(BaseModel):
    org_id: Optional[uuid.UUID] = None
    team_id: Optional[uuid.UUID] = None
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    auth_provider: Optional[str] = None


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
