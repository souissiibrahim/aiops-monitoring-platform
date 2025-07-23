from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class RunbookBase(BaseModel):
    name: str
    description: Optional[str]
    incident_type_id: Optional[UUID]
    service_id: Optional[UUID]
    team_id: Optional[UUID]
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
        #orm_mode = True
        from_attributes = True
