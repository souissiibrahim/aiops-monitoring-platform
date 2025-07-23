from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, DateTime, Boolean, func

Base = declarative_base()

class TimestampMixin:
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime, nullable=True)
