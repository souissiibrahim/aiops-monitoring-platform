from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class EndpointTypeBase(BaseModel):
    name: str
    category: Optional[str] = None
    description: Optional[str] = None


class EndpointTypeCreate(EndpointTypeBase):
    pass


class EndpointTypeUpdate(EndpointTypeBase):
    pass


class EndpointTypeInDB(EndpointTypeBase):
    endpoint_type_id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_deleted: Optional[bool] = False
    deleted_at: Optional[datetime] = None

    class Config:
        orm_mode = True
