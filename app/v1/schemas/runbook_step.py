from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class RunbookStepBase(BaseModel):
    runbook_id: UUID
    step_number: int
    action_type: Optional[str]
    description: Optional[str]
    command_or_script: Optional[str]
    timeout_minutes: Optional[int]
    success_condition: Optional[str]


class RunbookStepCreate(RunbookStepBase):
    pass


class RunbookStepUpdate(RunbookStepBase):
    pass


class RunbookStepInDB(RunbookStepBase):
    step_id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_deleted: Optional[bool] = False
    deleted_at: Optional[datetime] = None

    class Config:
        #orm_mode = True
        from_attributes = True
