from uuid import UUID
from typing import Optional, Dict
from pydantic import BaseModel
from datetime import datetime

from app.v1.schemas.endpoint_type import EndpointTypeInDB
from app.v1.schemas.environment import EnvironmentInDB
from app.v1.schemas.location import LocationInDB


class TelemetrySourceBase(BaseModel):
    name: str
    endpoint_type_id: Optional[UUID]
    environment_id: Optional[UUID]
    location_id: Optional[UUID]
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
        from_attributes = True


class TelemetrySourceRead(BaseModel):
    source_id: UUID
    name: str
    metadata_info: Optional[Dict]

    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_deleted: Optional[bool] = False
    deleted_at: Optional[datetime] = None

    # Nested objects instead of UUIDs
    endpoint_type: Optional[EndpointTypeInDB]
    environment: Optional[EnvironmentInDB]
    location: Optional[LocationInDB]

    class Config:
        from_attributes = True
