from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class IncidentTypeBase(BaseModel):
    name: str
    description: Optional[str] = None
    category: Optional[str] = None


class IncidentTypeCreate(IncidentTypeBase):
    pass


class IncidentTypeRead(IncidentTypeBase):
    incident_type_id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        #orm_mode = True
        from_attributes = True
