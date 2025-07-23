from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ShapExplanationBase(BaseModel):
    explanation_text: Optional[str] = None


class ShapExplanationCreate(ShapExplanationBase):
    pass


class ShapExplanationRead(ShapExplanationBase):
    explanation_id: UUID
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        orm_mode = True
