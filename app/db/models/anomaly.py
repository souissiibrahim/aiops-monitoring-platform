from sqlalchemy import Column, String, Float, Boolean, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from uuid import uuid4

from app.db.base import Base, TimestampMixin


class Anomaly(TimestampMixin, Base):
    __tablename__ = "anomalies"

    anomaly_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("telemetry_sources.source_id"), nullable=False)
    metric_type = Column(String(50), nullable=False)
    value = Column(Float, nullable=False)
    predicted_value = Column(Float)
    confidence_score = Column(Float)
    is_confirmed = Column(Boolean, default=False)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.incident_id"), nullable=True)
    detection_method = Column(String(50))
    timestamp = Column(DateTime, nullable=False)
    anomaly_metadata = Column(JSONB)

    # Relationships
    incident = relationship("Incident", back_populates="anomalies")
    telemetry_source = relationship("TelemetrySource", back_populates="anomalies")
