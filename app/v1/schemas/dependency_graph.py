from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from datetime import datetime

class DependencyGraphBase(BaseModel):
    dependent_service_id: UUID
    dependency_service_id: UUID
    dependency_type: Optional[str] = None
    weight: Optional[float] = None

class DependencyGraphCreate(DependencyGraphBase):
    pass

class DependencyGraphUpdate(DependencyGraphBase):
    pass

class DependencyGraphInDB(DependencyGraphBase):
    dependency_id: UUID
    #last_updated: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_deleted: Optional[bool] = False
    deleted_at: Optional[datetime] = None

    class Config:
        #orm_mode = True
        from_attributes = True
