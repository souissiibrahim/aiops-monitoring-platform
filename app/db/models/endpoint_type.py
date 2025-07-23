from sqlalchemy import Column, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from uuid import uuid4

from app.db.base import Base, TimestampMixin


class EndpointType(TimestampMixin, Base):
    __tablename__ = "endpoint_types"

    endpoint_type_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(100), unique=True, nullable=False)
    category = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)

    telemetry_sources = relationship("TelemetrySource", back_populates="endpoint_type", cascade="all, delete-orphan")
