from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from uuid import uuid4

from app.db.base import Base, TimestampMixin


class RunbookStep(TimestampMixin, Base):
    __tablename__ = "runbook_steps"

    step_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    runbook_id = Column(UUID(as_uuid=True), ForeignKey("runbooks.runbook_id"), nullable=False)

    step_number = Column(Integer, nullable=False)
    action_type = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    command_or_script = Column(Text, nullable=True)
    timeout_minutes = Column(Integer, nullable=True)
    success_condition = Column(String(255), nullable=True)

    # Relationship
    runbook = relationship("Runbook", back_populates="runbook_steps")
    response_actions = relationship("ResponseAction", back_populates="step", cascade="all, delete-orphan")
