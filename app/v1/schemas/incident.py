from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class IncidentBase(BaseModel):
    service_id: UUID
    source_id: UUID
    incident_type_id: UUID
    severity_level_id: UUID
    status_id: UUID
    root_cause_id: Optional[UUID] = None
    start_timestamp: datetime
    end_timestamp: Optional[datetime] = None
    description: Optional[str] = None
    escalation_level: Optional[str] = "Level1"


class IncidentCreate(IncidentBase):
    pass


class IncidentRead(IncidentBase):
    incident_id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        #orm_mode = True
        from_attributes = True
