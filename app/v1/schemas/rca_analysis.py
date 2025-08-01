from __future__ import annotations
from uuid import UUID
from datetime import datetime
from typing import Optional, List, Dict, TYPE_CHECKING
from pydantic import BaseModel, Field
from app.v1.schemas.telemetry_source import TelemetrySourceRead
from app.v1.schemas.team import TeamInDB

if TYPE_CHECKING:
    from app.v1.schemas.incident import IncidentRead  


class RecommendationItem(BaseModel):
    text: str
    confidence: float


class RCAAnalysisBase(BaseModel):
    incident_id: UUID
    analysis_method: str
    root_cause_node_id: Optional[UUID] = None
    confidence_score: Optional[float] = None
    contributing_factors: Optional[Dict[str, float]] = None
    #recommendations: Optional[List[str]] = None
    recommendations: Optional[List[RecommendationItem]] = None
    analysis_timestamp: datetime
    analyst_team_id: Optional[UUID] = None

class RCAAnalysisCreate(RCAAnalysisBase):
    pass

class RCAAnalysisInDB(RCAAnalysisBase):
    rca_id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True

class RCAAnalysisLite(BaseModel):
    rca_id: UUID
    analysis_method: str
    root_cause_node_id: Optional[UUID]
    confidence_score: Optional[float]
    contributing_factors: Optional[Dict[str, float]]
    #recommendations: Optional[List[str]]
    recommendations: Optional[List[RecommendationItem]] = None
    analysis_timestamp: datetime
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    team: Optional[TeamInDB]

    class Config:
        from_attributes = True

class RCAAnalysisRead(BaseModel):
    rca_id: UUID
    analysis_method: str
    root_cause_node_id: Optional[UUID]
    confidence_score: Optional[float]
    contributing_factors: Optional[Dict[str, float]]
    #recommendations: Optional[List[str]]
    recommendations: Optional[List[RecommendationItem]] = None
    analysis_timestamp: datetime
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    incident: Optional["IncidentRead"]
    team: Optional[TeamInDB] = Field(default=None)
    root_cause_node: Optional[TelemetrySourceRead] = Field(default=None)

    class Config:
        from_attributes = True
