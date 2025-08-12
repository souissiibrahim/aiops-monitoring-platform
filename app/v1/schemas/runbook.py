from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from app.v1.schemas.incident_type import IncidentTypeRead
from app.v1.schemas.service import ServiceInDB
from app.v1.schemas.team import TeamInDB


class RunbookBase(BaseModel):
    runbook_id: Optional[UUID] = None  
    name: str
    description: Optional[str] = None
    incident_type_id: UUID
    service_id: Optional[UUID] = None
    team_id: Optional[UUID] = None
    priority: int


class RunbookCreate(RunbookBase):
    pass


class RunbookUpdate(RunbookBase):
    pass


class RunbookInDB(RunbookBase):
    runbook_id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_deleted: Optional[bool] = False
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RunbookRead(BaseModel):
    runbook_id: UUID
    name: str
    description: Optional[str]
    priority: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_deleted: Optional[bool]
    deleted_at: Optional[datetime]

    incident_type: Optional[IncidentTypeRead]
    service: Optional[ServiceInDB]
    team: Optional[TeamInDB]

    class Config:
        from_attributes = True
