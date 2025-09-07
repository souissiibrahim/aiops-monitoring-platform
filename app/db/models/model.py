import uuid
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB   # add JSONB
from app.db.base import Base, TimestampMixin
from sqlalchemy.orm import relationship


class Model(TimestampMixin, Base):
    __tablename__ = "models"

    model_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)
    version = Column(String, nullable=True)
    accuracy = Column(String, nullable=True)

    metrics = Column(JSONB, nullable=True)   

    last_trained_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_training_status = Column(String(16), nullable=True, index=True)  

    predictions = relationship("Prediction", back_populates="model")
