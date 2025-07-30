from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from datetime import datetime

from app.v1.schemas.incident import IncidentRead
from app.v1.schemas.runbook import RunbookRead
from app.v1.schemas.runbook_step import RunbookStepRead
from app.v1.schemas.team import TeamInDB



class ResponseActionBase(BaseModel):
    incident_id: UUID
    runbook_id: UUID
    step_id: UUID
    executed_by_team_id: Optional[UUID]
    status: Optional[str] = "Pending"
    execution_log: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]


class ResponseActionCreate(ResponseActionBase):
    pass


class ResponseActionUpdate(ResponseActionBase):
    pass



class ResponseActionInDB(ResponseActionBase):
    action_id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_deleted: Optional[bool] = False
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True



class ResponseActionRead(BaseModel):
    action_id: UUID
    status: Optional[str]
    execution_log: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_deleted: Optional[bool] = False
    deleted_at: Optional[datetime] = None

    incident: Optional[IncidentRead]
    runbook: Optional[RunbookRead]
    step: Optional[RunbookStepRead]
    team: Optional[TeamInDB]
    class Config:
        from_attributes = True
