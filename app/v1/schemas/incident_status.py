from uuid import UUID
from typing import Optional
from pydantic import BaseModel


class IncidentStatusBase(BaseModel):
    name: str
    description: Optional[str] = None


class IncidentStatusCreate(IncidentStatusBase):
    pass


class IncidentStatusRead(IncidentStatusBase):
    status_id: UUID

    class Config:
        #orm_mode = True
        from_attributes = True
