import uuid
from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base, TimestampMixin
from sqlalchemy.orm import relationship


class Model(TimestampMixin, Base):
    __tablename__ = "models"

    model_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)
    version = Column(String, nullable=True)
    accuracy = Column(String, nullable=True)


    predictions = relationship("Prediction", back_populates="model")