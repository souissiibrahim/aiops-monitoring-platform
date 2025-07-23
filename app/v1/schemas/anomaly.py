from uuid import UUID
from typing import Optional, Dict
from pydantic import BaseModel
from datetime import datetime


class AnomalyBase(BaseModel):
    source_id: UUID
    metric_type: str
    value: float
    predicted_value: Optional[float]
    confidence_score: Optional[float]
    is_confirmed: Optional[bool] = False
    incident_id: Optional[UUID]
    detection_method: Optional[str]
    timestamp: datetime
    anomaly_metadata: Optional[Dict] = None


class AnomalyCreate(AnomalyBase):
    pass


class AnomalyUpdate(AnomalyBase):
    pass


class AnomalyInDB(AnomalyBase):
    anomaly_id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    is_deleted: Optional[bool] = False
    deleted_at: Optional[datetime] = None

    class Config:
        orm_mode = True
