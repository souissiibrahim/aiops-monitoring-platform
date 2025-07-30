from sqlalchemy import Column, String, Text
from sqlalchemy.dialects.postgresql import UUID
from uuid import uuid4
from sqlalchemy.orm import relationship
from app.db.base import Base, TimestampMixin


class Team(TimestampMixin, Base):
    __tablename__ = "teams"

    team_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    contact_email = Column(String(255), nullable=True)
    slack_channel = Column(String(100), nullable=True)

    # Optional relationships:
    owned_services = relationship("Service", back_populates="owner_team", cascade="all, delete-orphan")
    runbooks = relationship("Runbook", back_populates="team", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="team", cascade="all, delete-orphan")
    # services = relationship("Service", back_populates="owner_team")
    # runbooks = relationship("Runbook", back_populates="team")
    response_actions = relationship("ResponseAction", back_populates="team", cascade="all, delete-orphan")
    # response_actions = relationship("ResponseAction", back_populates="executed_by_team")
    # rca_analysis = relationship("RCAAnalysis", back_populates="analyst_team")
    team_endpoint_ownerships = relationship("TeamEndpointOwnership", back_populates="team", cascade="all, delete-orphan")
    rca_analyses = relationship("RCAAnalysis", back_populates="team")

