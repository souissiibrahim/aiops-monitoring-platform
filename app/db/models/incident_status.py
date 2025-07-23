from sqlalchemy import Column, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from uuid import uuid4

from app.db.base import Base, TimestampMixin


class IncidentStatus(TimestampMixin, Base):
    __tablename__ = "incident_statuses"

    status_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(20), unique=True, nullable=False)
    description = Column(Text, nullable=True)

    # Relationship to incidents
    incidents = relationship("Incident", back_populates="status", cascade="all, delete-orphan")
