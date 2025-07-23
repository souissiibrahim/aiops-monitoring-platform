from uuid import UUID
from typing import Optional, Dict
from pydantic import BaseModel
from datetime import datetime


class PredictionBase(BaseModel):
    model_id: Optional[UUID]
    input_features: Dict
    prediction_output: Dict
    confidence_score: Optional[float]
    prediction_timestamp: Optional[datetime] = None
    incident_id: Optional[UUID]
    status: Optional[str] = "Pending"
    explanation_id: Optional[UUID]


class PredictionCreate(PredictionBase):
    pass


class PredictionUpdate(PredictionBase):
    pass


class PredictionInDB(PredictionBase):
    prediction_id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_deleted: Optional[bool] = False
    deleted_at: Optional[datetime] = None

    class Config:
        orm_mode = True
