from sqlalchemy import Column, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from uuid import uuid4

from app.db.base import Base, TimestampMixin


class Service(TimestampMixin, Base):
    __tablename__ = "services"

    service_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    criticality_level = Column(String(20), default="Medium")
    owner_team_id = Column(UUID(as_uuid=True), ForeignKey("teams.team_id"))

    # Relationships
    owner_team = relationship("Team", back_populates="owned_services")
    incidents = relationship("Incident", back_populates="service", cascade="all, delete-orphan")
    runbooks = relationship("Runbook", back_populates="service", cascade="all, delete-orphan")
    service_endpoints = relationship("ServiceEndpoint", back_populates="service", cascade="all, delete-orphan")
    dependencies = relationship("DependencyGraph", back_populates="dependent_service", foreign_keys="DependencyGraph.dependent_service_id", cascade="all, delete-orphan")
    dependents = relationship("DependencyGraph", back_populates="dependency_service", foreign_keys="DependencyGraph.dependency_service_id", cascade="all, delete-orphan")
