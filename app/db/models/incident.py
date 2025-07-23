from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from uuid import uuid4

from app.db.base import Base, TimestampMixin


class Incident(TimestampMixin, Base):
    __tablename__ = "incidents"

    incident_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    service_id = Column(UUID(as_uuid=True), ForeignKey("services.service_id"), nullable=False)
    source_id = Column(UUID(as_uuid=True), ForeignKey("telemetry_sources.source_id"), nullable=False)
    incident_type_id = Column(UUID(as_uuid=True), ForeignKey("incident_types.incident_type_id"), nullable=False)
    severity_level_id = Column(UUID(as_uuid=True), ForeignKey("severity_levels.severity_level_id"), nullable=False)
    status_id = Column(UUID(as_uuid=True), ForeignKey("incident_statuses.status_id"), nullable=False)
    #root_cause_id = Column(UUID(as_uuid=True), ForeignKey("rca_analysis.rca_id"), nullable=True)
    root_cause_id = Column(UUID, ForeignKey('rca_analysis.rca_id', use_alter=True, name="fk_incident_root_cause", deferrable=True, initially='DEFERRED'))
    start_timestamp = Column(DateTime, nullable=False)
    end_timestamp = Column(DateTime, nullable=True)
    description = Column(Text, nullable=True)
    escalation_level = Column(String(20), default="Level1")

    # === Relationships ===
    service = relationship("Service", back_populates="incidents")
    source = relationship("TelemetrySource", back_populates="incidents")
    incident_type = relationship("IncidentType", back_populates="incidents")
    severity_level = relationship("SeverityLevel", back_populates="incidents")
    status = relationship("IncidentStatus", back_populates="incidents")
    #root_cause = relationship("RCAAnalysis", back_populates="incident", uselist=False)
    root_cause = relationship("RCAAnalysis", back_populates="incident", uselist=False, foreign_keys=[root_cause_id])
    anomalies = relationship("Anomaly", back_populates="incident", cascade="all, delete-orphan")
    predictions = relationship("Prediction", back_populates="incident", cascade="all, delete-orphan")
    response_actions = relationship("ResponseAction", back_populates="incident", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="incident", cascade="all, delete-orphan")
