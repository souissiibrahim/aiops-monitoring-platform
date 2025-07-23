from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class LocationBase(BaseModel):
    name: str
    region_code: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class LocationCreate(LocationBase):
    pass


class LocationUpdate(LocationBase):
    pass


class LocationInDB(LocationBase):
    location_id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_deleted: Optional[bool] = False
    deleted_at: Optional[datetime] = None

    class Config:
        orm_mode = True
