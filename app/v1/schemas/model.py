from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from typing import Optional


class ModelBase(BaseModel):
    name: str
    type: str
    version: Optional[str] = None
    accuracy: Optional[float] = None

    last_trained_at: Optional[datetime] = None
    last_training_status: Optional[str] = None


class ModelCreate(ModelBase):
    pass


class ModelUpdate(ModelBase):
    pass


class ModelOut(ModelBase):
    model_id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_deleted: Optional[bool] = False
    deleted_at: Optional[datetime] = None

    class Config:
        #orm_mode = True
        from_attributes = True
