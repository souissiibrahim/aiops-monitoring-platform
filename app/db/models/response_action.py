from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from uuid import uuid4

from app.db.base import Base, TimestampMixin


class ResponseAction(TimestampMixin, Base):
    __tablename__ = "response_actions"

    action_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.incident_id"))
    runbook_id = Column(UUID(as_uuid=True), ForeignKey("runbooks.runbook_id"))
    step_id = Column(UUID(as_uuid=True), ForeignKey("runbook_steps.step_id"))
    executed_by_team_id = Column(UUID(as_uuid=True), ForeignKey("teams.team_id"))

    status = Column(String(20), default="Pending")  # Pending / In Progress / Completed / Failed
    execution_log = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(Text)

    # Relationships
    incident = relationship("Incident", back_populates="response_actions")
    runbook = relationship("Runbook", back_populates="response_actions")
    step = relationship("RunbookStep", back_populates="response_actions")
    team = relationship("Team", back_populates="response_actions")
