import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import UserRole


class UserBase(BaseModel):
    org_id: uuid.UUID
    team_id: uuid.UUID
    name: str
    email: EmailStr
    auth_provider: Optional[str] = None
    role: UserRole = UserRole.MEMBER


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=72)


class UserUpdate(BaseModel):
    org_id: Optional[uuid.UUID] = None
    team_id: Optional[uuid.UUID] = None
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    auth_provider: Optional[str] = None
    role: Optional[UserRole] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=72)


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
