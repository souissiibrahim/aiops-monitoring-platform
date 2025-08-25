from uuid import UUID
from typing import Optional, Dict
from pydantic import BaseModel, Field
from datetime import datetime
from app.v1.schemas.model import ModelOut
from app.v1.schemas.shap_explanation import ShapExplanationRead


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
    model: Optional[ModelOut] = None
    explanation: Optional[ShapExplanationRead] = None

    model_id: Optional[UUID] = Field(default=None, exclude=True)
    explanation_id: Optional[UUID] = Field(default=None, exclude=True)

    class Config:
        #orm_mode = True
        from_attributes = True
