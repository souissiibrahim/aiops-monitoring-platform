from uuid import UUID
from typing import Optional, Dict
from pydantic import BaseModel
from datetime import datetime


class TelemetrySourceBase(BaseModel):
    name: str
    endpoint_type_id: UUID
    environment_id: UUID
    location_id: UUID
    metadata_info: Optional[Dict] = None


class TelemetrySourceCreate(TelemetrySourceBase):
    pass


class TelemetrySourceUpdate(TelemetrySourceBase):
    pass


class TelemetrySourceInDB(TelemetrySourceBase):
    source_id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_deleted: Optional[bool] = False
    deleted_at: Optional[datetime] = None

    class Config:
        #orm_mode = True
        from_attributes = True
