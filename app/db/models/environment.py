from sqlalchemy import Column, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from uuid import uuid4

from app.db.base import Base, TimestampMixin    


class Environment(TimestampMixin, Base):
    __tablename__ = "environments"

    environment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(Text, nullable=True)

    # Relationships
    telemetry_sources = relationship("TelemetrySource", back_populates="environment", cascade="all, delete-orphan")
