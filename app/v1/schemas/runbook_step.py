from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from datetime import datetime

from app.v1.schemas.runbook import RunbookRead  # ✅ import nested schema


# === Base Schema ===
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


# === Internal Flat DB Schema ===
class RunbookStepInDB(RunbookStepBase):
    step_id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_deleted: Optional[bool] = False
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RunbookStepRead(BaseModel):
    step_id: UUID
    step_number: int
    action_type: Optional[str]
    description: Optional[str]
    command_or_script: Optional[str]
    timeout_minutes: Optional[int]
    success_condition: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_deleted: Optional[bool] = False
    deleted_at: Optional[datetime] = None

    runbook: Optional[RunbookRead]  

    class Config:
        from_attributes = True
