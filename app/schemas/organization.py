import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict


class OrganizationBase(BaseModel):
    name: str
    logo_url: Optional[str] = None


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    logo_url: Optional[str] = None


class OrganizationRead(OrganizationBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
