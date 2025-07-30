from __future__ import annotations
from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from app.v1.schemas.service import ServiceInDB
from app.v1.schemas.telemetry_source import TelemetrySourceRead
from app.v1.schemas.incident_type import IncidentTypeRead
from app.v1.schemas.severity_level import SeverityLevelInDB
from app.v1.schemas.incident_status import IncidentStatusRead

# ⛔ avoid circular recursion by using RCAAnalysisLite
from app.v1.schemas.rca_analysis import RCAAnalysisLite, RCAAnalysisRead

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
    title: Optional[str] = None

class IncidentCreate(IncidentBase):
    pass

class IncidentRead(BaseModel):
    incident_id: UUID
    title: Optional[str]
    description: Optional[str]
    escalation_level: Optional[str]
    start_timestamp: datetime
    end_timestamp: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    service: Optional[ServiceInDB]
    source: Optional[TelemetrySourceRead]
    incident_type: Optional[IncidentTypeRead]
    severity_level: Optional[SeverityLevelInDB]
    status: Optional[IncidentStatusRead]
    root_cause: Optional[RCAAnalysisLite]

    class Config:
        from_attributes = True


RCAAnalysisRead.model_rebuild()
IncidentRead.model_rebuild()
