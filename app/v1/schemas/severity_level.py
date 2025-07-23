from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class SeverityLevelBase(BaseModel):
    name: str
    impact_score: int
    description: Optional[str] = None
    sla_hours: int


class SeverityLevelCreate(SeverityLevelBase):
    pass


class SeverityLevelUpdate(SeverityLevelBase):
    pass


class SeverityLevelInDB(SeverityLevelBase):
    severity_level_id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_deleted: Optional[bool] = False
    deleted_at: Optional[datetime] = None

    class Config:
        orm_mode = True
