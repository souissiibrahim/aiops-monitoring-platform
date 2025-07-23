from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class ServiceEndpointBase(BaseModel):
    service_id: UUID
    source_id: UUID
    role_in_service: Optional[str] = None


class ServiceEndpointCreate(ServiceEndpointBase):
    pass


class ServiceEndpointUpdate(ServiceEndpointBase):
    pass


class ServiceEndpointInDB(ServiceEndpointBase):
    service_endpoint_id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_deleted: Optional[bool]
    deleted_at: Optional[datetime]

    class Config:
        orm_mode = True
