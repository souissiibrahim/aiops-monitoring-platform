from sqlalchemy import Column, Boolean, Date, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from uuid import uuid4

from app.db.base import Base, TimestampMixin


class TeamEndpointOwnership(TimestampMixin, Base):
    __tablename__ = "team_endpoint_ownership"

    ownership_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.team_id"), nullable=False)
    source_id = Column(UUID(as_uuid=True), ForeignKey("telemetry_sources.source_id"), nullable=False)
    is_primary = Column(Boolean, default=False)
    start_date = Column(Date)
    end_date = Column(Date)

    __table_args__ = (UniqueConstraint('team_id', 'source_id', name='uq_team_source'),)

    #team = relationship("Team", backref="owned_sources")
    team = relationship("Team", back_populates="team_endpoint_ownerships")
    #source = relationship("TelemetrySource", backref="owning_teams")
    source = relationship("TelemetrySource", back_populates="team_ownerships")
