from uuid import UUID
from typing import Optional
from pydantic import BaseModel, EmailStr
from datetime import datetime


class TeamBase(BaseModel):
    name: str
    description: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    slack_channel: Optional[str] = None


class TeamCreate(TeamBase):
    pass


class TeamUpdate(TeamBase):
    pass


class TeamInDB(TeamBase):
    team_id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_deleted: Optional[bool] = False
    deleted_at: Optional[datetime] = None

    class Config:
        orm_mode = True
