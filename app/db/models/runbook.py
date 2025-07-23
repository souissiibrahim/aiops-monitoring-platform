from sqlalchemy import Column, String, Text, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from uuid import uuid4

from app.db.base import Base, TimestampMixin


class Runbook(TimestampMixin, Base):
    __tablename__ = "runbooks"

    runbook_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text)

    incident_type_id = Column(UUID(as_uuid=True), ForeignKey("incident_types.incident_type_id"))
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.service_id"))
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.team_id"))

    priority = Column(Integer, nullable=False)

    # Relationships
    incident_type = relationship("IncidentType", back_populates="runbooks")
    service = relationship("Service", back_populates="runbooks")
    team = relationship("Team", back_populates="runbooks")
    response_actions = relationship("ResponseAction", back_populates="runbook", cascade="all, delete-orphan")
    runbook_steps = relationship("RunbookStep", back_populates="runbook", cascade="all, delete-orphan")
