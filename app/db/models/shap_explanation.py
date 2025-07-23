from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base, TimestampMixin
import uuid

class ShapExplanation(TimestampMixin, Base):
    __tablename__ = "shap_explanations"

    explanation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    explanation_text = Column(String)
