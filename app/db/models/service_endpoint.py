from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from uuid import uuid4

from app.db.base import Base, TimestampMixin


class ServiceEndpoint(TimestampMixin, Base):
    __tablename__ = "service_endpoints"

    service_endpoint_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.service_id"))
    source_id = Column(UUID(as_uuid=True), ForeignKey("telemetry_sources.source_id"))
    role_in_service = Column(String(100), nullable=True)

    service = relationship("Service", back_populates="service_endpoints")
    telemetry_source = relationship("TelemetrySource", back_populates="service_endpoints")
