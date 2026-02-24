from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, Literal

class ChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = None 
    conversation_id: Optional[str] = None
    use_memory: bool = True

class ChatResponse(BaseModel):
    reply: str
    conversation_id: str
    timestamp: datetime

# Auth Models
class UserRegister(BaseModel):
    email: EmailStr
    password: str
    name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class GoogleAuth(BaseModel):
    token: str  # Google ID token

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    avatar: Optional[str] = None
    role: Literal["free", "pro", "enterprise"] = "free"
    message_count: int = 0
    message_limit: int = 100
    is_active: bool = True
    created_at: datetime

class PaymentInitiate(BaseModel):
    plan: str  # "pro_monthly", "pro_yearly"

class PaymentVerify(BaseModel):
    reference: str