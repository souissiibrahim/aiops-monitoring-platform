from sqlalchemy import Column, String, Text, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from uuid import uuid4

from app.db.base import Base, TimestampMixin


class SeverityLevel(TimestampMixin, Base):
    __tablename__ = "severity_levels"

    severity_level_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(20), unique=True, nullable=False)
    impact_score = Column(Integer, nullable=False)
    description = Column(Text, nullable=True)
    sla_hours = Column(Integer, nullable=False)

    # Relationship to Incident
    incidents = relationship("Incident", back_populates="severity_level", cascade="all, delete-orphan")
