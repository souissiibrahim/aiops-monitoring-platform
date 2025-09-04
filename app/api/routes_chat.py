from fastapi import APIRouter
from pydantic import BaseModel
from app.chat.agent import answer

router = APIRouter(prefix="/chat", tags=["assistant"])

class AskIn(BaseModel):
    question: str
    user: str | None = None

class AskOut(BaseModel):
    ok: bool
    text: str
    sources: list[str] = []

@router.post("/ask", response_model=AskOut)
def chat_ask(inb: AskIn):
    return AskOut(**answer(inb.question, user=inb.user))
