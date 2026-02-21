from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class ChatRequest(BaseModel):
    message: str
    user_id: str
    conversation_id: Optional[str] = None
    use_memory: bool = True

class ChatResponse(BaseModel):
    reply: str
    conversation_id: str
    timestamp: datetime

class ConversationCreate(BaseModel):
    user_id: str
    title: str