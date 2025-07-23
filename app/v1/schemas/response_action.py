from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from datetime import datetime


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
        orm_mode = True
