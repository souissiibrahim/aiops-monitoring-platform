from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from uuid import uuid4

from app.db.base import Base, TimestampMixin


class AuditLog(TimestampMixin, Base):
    __tablename__ = "audit_logs"

    log_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(100), nullable=True)
    entity_id = Column(UUID(as_uuid=True), nullable=True)

    old_value = Column(JSONB, nullable=True)
    new_value = Column(JSONB, nullable=True)

    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.incident_id"), nullable=True)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.team_id"), nullable=True)

    timestamp = Column(DateTime, nullable=False)

    # Relationships
    incident = relationship("Incident", back_populates="audit_logs")
    team = relationship("Team", back_populates="audit_logs")
