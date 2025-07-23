from sqlalchemy import Column, Float, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from uuid import uuid4
from datetime import datetime

from app.db.base import Base, TimestampMixin


class Prediction(TimestampMixin, Base):
    __tablename__ = "predictions"

    prediction_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    model_id = Column(UUID(as_uuid=True), ForeignKey("models.model_id"), nullable=True)
    input_features = Column(JSONB, nullable=False)
    prediction_output = Column(JSONB, nullable=False)
    confidence_score = Column(Float)
    prediction_timestamp = Column(DateTime, default=datetime.utcnow)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.incident_id"), nullable=True)
    status = Column(String(20), default="Pending")  # Pending / Validated / Invalid
    explanation_id = Column(UUID(as_uuid=True), ForeignKey("shap_explanations.explanation_id"), nullable=True)

    # Relationships
    incident = relationship("Incident", back_populates="predictions")
