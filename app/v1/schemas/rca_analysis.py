from uuid import UUID
from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel


class RCAAnalysisBase(BaseModel):
    incident_id: UUID
    analysis_method: str
    root_cause_node_id: Optional[UUID] = None
    confidence_score: Optional[float] = None
    contributing_factors: Optional[Dict[str, float]] = None
    recommendations: Optional[List[str]] = None
    analysis_timestamp: datetime
    analyst_team_id: Optional[UUID] = None


class RCAAnalysisCreate(RCAAnalysisBase):
    pass


class RCAAnalysisRead(RCAAnalysisBase):
    rca_id: UUID

    class Config:
        orm_mode = True
