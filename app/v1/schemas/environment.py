from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class EnvironmentBase(BaseModel):
    name: str
    description: Optional[str] = None


class EnvironmentCreate(EnvironmentBase):
    pass


class EnvironmentUpdate(EnvironmentBase):
    pass


class EnvironmentInDB(EnvironmentBase):
    environment_id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_deleted: Optional[bool] = False
    deleted_at: Optional[datetime] = None

    class Config:
        orm_mode = True
