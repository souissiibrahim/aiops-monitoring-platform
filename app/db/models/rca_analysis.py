from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from uuid import uuid4
from app.db.models.incident import Incident
from app.db.base import Base, TimestampMixin
from app.db.models.telemetry_source import TelemetrySource


class RCAAnalysis(TimestampMixin, Base):
    __tablename__ = "rca_analysis"

    rca_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.incident_id"), nullable=False)
    analysis_method = Column(String(50), nullable=False)
    #root_cause_node_id = Column(UUID(as_uuid=True), nullable=True)
    root_cause_node_id = Column(UUID(as_uuid=True), ForeignKey("telemetry_sources.source_id"), nullable=True)  # ✅ FK to telemetry_sources

    confidence_score = Column(Float, nullable=True)
    contributing_factors = Column(JSON, nullable=True)
    recommendations = Column(ARRAY(Text), nullable=True)
    analysis_timestamp = Column(DateTime, nullable=False)

    analyst_team_id = Column(UUID(as_uuid=True), ForeignKey("teams.team_id"), nullable=True)

    
    incident = relationship("Incident", back_populates="root_cause", foreign_keys=[Incident.root_cause_id], uselist=False)
    team = relationship("Team", back_populates="rca_analyses", foreign_keys=[analyst_team_id])
    root_cause_node = relationship("TelemetrySource", foreign_keys=[root_cause_node_id])