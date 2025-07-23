from sqlalchemy import Column, String, Float, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from uuid import uuid4
from datetime import datetime

from app.db.base import Base, TimestampMixin

class DependencyGraph(TimestampMixin, Base):
    __tablename__ = "dependency_graph"

    dependency_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    dependent_service_id = Column(UUID(as_uuid=True), ForeignKey("services.service_id"))
    dependency_service_id = Column(UUID(as_uuid=True), ForeignKey("services.service_id"))
    dependency_type = Column(String(50))
    weight = Column(Float)
    #last_updated = Column(DateTime, default=datetime.utcnow)

    dependent_service = relationship("Service", foreign_keys=[dependent_service_id], back_populates="dependencies")
    dependency_service = relationship("Service", foreign_keys=[dependency_service_id])
