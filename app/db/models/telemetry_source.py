from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from uuid import uuid4

from app.db.base import Base, TimestampMixin


class TelemetrySource(TimestampMixin, Base):
    __tablename__ = "telemetry_sources"

    source_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)

    endpoint_type_id = Column(UUID(as_uuid=True), ForeignKey("endpoint_types.endpoint_type_id"))
    environment_id = Column(UUID(as_uuid=True), ForeignKey("environments.environment_id"))
    location_id = Column(UUID(as_uuid=True), ForeignKey("locations.location_id"))

    metadata_info = Column(JSONB, nullable=True)

    # Relationships
    endpoint_type = relationship("EndpointType", back_populates="telemetry_sources")
    environment = relationship("Environment", back_populates="telemetry_sources")
    location = relationship("Location", back_populates="telemetry_sources")

    # Reverse relations
    incidents = relationship("Incident", back_populates="source", cascade="all, delete-orphan")
    #anomalies = relationship("Anomaly", back_populates="source", cascade="all, delete-orphan")
    anomalies = relationship("Anomaly", back_populates="telemetry_source", cascade="all, delete-orphan")
    #team_ownerships = relationship("TeamEndpointOwnership", back_populates="source", cascade="all, delete-orphan")
    team_ownerships = relationship("TeamEndpointOwnership", back_populates="source", cascade="all, delete-orphan")

    #service_endpoints = relationship("ServiceEndpoint", back_populates="source", cascade="all, delete-orphan")
    service_endpoints = relationship("ServiceEndpoint", back_populates="telemetry_source", cascade="all, delete-orphan")

