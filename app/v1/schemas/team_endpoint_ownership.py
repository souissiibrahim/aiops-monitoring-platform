from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from datetime import date, datetime


class TeamEndpointOwnershipBase(BaseModel):
    team_id: UUID
    source_id: UUID
    is_primary: Optional[bool] = False
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class TeamEndpointOwnershipCreate(TeamEndpointOwnershipBase):
    pass


class TeamEndpointOwnershipUpdate(TeamEndpointOwnershipBase):
    pass


class TeamEndpointOwnershipInDB(TeamEndpointOwnershipBase):
    ownership_id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_deleted: Optional[bool] = False
    deleted_at: Optional[datetime] = None

    class Config:
        #orm_mode = True
        from_attributes = True
