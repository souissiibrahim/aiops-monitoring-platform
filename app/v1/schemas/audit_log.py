from uuid import UUID
from typing import Optional, Any
from pydantic import BaseModel
from datetime import datetime


class AuditLogBase(BaseModel):
    user_id: Optional[UUID]
    action: str
    entity_type: Optional[str]
    entity_id: Optional[UUID]
    old_value: Optional[dict]
    new_value: Optional[dict]
    incident_id: Optional[UUID]
    team_id: Optional[UUID]
    timestamp: datetime


class AuditLogCreate(AuditLogBase):
    pass


class AuditLogUpdate(AuditLogBase):
    pass


class AuditLogInDB(AuditLogBase):
    log_id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_deleted: Optional[bool] = False
    deleted_at: Optional[datetime] = None

    class Config:
        #orm_mode = True
        from_attributes = True
