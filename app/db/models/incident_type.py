from sqlalchemy import Column, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from uuid import uuid4

from app.db.base import Base, TimestampMixin


class IncidentType(TimestampMixin, Base):
    __tablename__ = "incident_types"

    incident_type_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=True)

    # Relationship to incidents
    incidents = relationship("Incident", back_populates="incident_type", cascade="all, delete-orphan")
    runbooks = relationship("Runbook", back_populates="incident_type", cascade="all, delete-orphan")