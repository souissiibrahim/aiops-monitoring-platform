from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    criticality_level: Optional[str] = "Medium"
    owner_team_id: Optional[UUID]


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(ServiceBase):
    pass


class ServiceInDB(ServiceBase):
    service_id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_deleted: Optional[bool] = False
    deleted_at: Optional[datetime] = None

    class Config:
        orm_mode = True
