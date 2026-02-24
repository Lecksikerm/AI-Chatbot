from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import uuid
from datetime import datetime

from app.models import ChatRequest, ChatResponse 
from app.chatbot import chatbot
from app.db import db
from app.auth import get_current_active_user

# Import routers
from app.routers import auth
from app.routers import payment

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(" AI SaaS Backend starting...")
    # Create indexes for users collection
    try:
        db.db.users.create_index([("email", 1)], unique=True)
        db.db.users.create_index([("google_id", 1)], sparse=True)
        logger.info("✅ User indexes created")
    except Exception as e:
        logger.warning(f"Index creation warning: {e}")
    yield
    logger.info("🛑 AI SaaS Backend shutting down...")

app = FastAPI(
    title="AI SaaS API",
    description="ChatGPT-style AI SaaS powered by Gemini",
    version="2.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "https://lecksibot.vercel.app",
        "https://ai-saa-s-chatbot.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include auth router
app.include_router(auth.router)
app.include_router(payment.router)

@app.get("/")
async def root():
    return {
        "message": "AI SaaS API is running! 🤖",
        "docs": "/docs",
        "health": "/health",
        "version": "2.0.0",
        "auth": "/auth"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        db.client.admin.command('ping')
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "2.0.0"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")
    
@app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest, 
    current_user: dict = Depends(get_current_active_user)
):
    """Chat endpoint with authentication and MEMORY"""
    try:
        # Get user_id from JWT token, ignore request body user_id
        user_id = current_user["id"]
        conv_id = req.conversation_id or str(uuid.uuid4())
        
        # Check message limits for free tier
        if current_user.get("role") == "free":
            msg_count = current_user.get("message_count", 0)
            msg_limit = current_user.get("message_limit", 100)
            if msg_count >= msg_limit:
                raise HTTPException(
                    status_code=429,
                    detail="Message limit reached. Upgrade to Pro to continue."
                )
        
        # Load history
        history = []
        if req.use_memory:
            history = list(db.messages.find(
                {"conversation_id": conv_id, "user_id": user_id},
                {"_id": 0, "user_message": 1, "bot_reply": 1}
            ).sort("timestamp", 1))
            logger.info(f"🧠 Loaded {len(history)} messages from history")
        
        # Get AI response
        reply = chatbot.ask_ai(
            message=req.message,
            user_id=user_id,
            conversation_id=conv_id,
            history=history if req.use_memory else None
        )
        
        # Store in MongoDB
        message_doc = {
            "user_id": user_id,
            "conversation_id": conv_id,
            "user_message": req.message,
            "bot_reply": reply,
            "timestamp": datetime.utcnow(),
            "model": "gemini-1.5-flash"
        }
        db.messages.insert_one(message_doc)
        
        # Increment message count for free tier tracking
        if current_user.get("role") == "free":
            db.users.update_one(
                {"id": user_id},
                {"$inc": {"message_count": 1}}
            )
        
        # Update conversation metadata
        db.conversations.update_one(
            {"id": conv_id, "user_id": user_id},
            {
                "$set": {
                    "user_id": user_id,
                    "id": conv_id,
                    "updated_at": datetime.utcnow()
                },
                "$setOnInsert": {
                    "created_at": datetime.utcnow(),
                    "title": req.message[:50] + "..." if len(req.message) > 50 else req.message
                }
            },
            upsert=True
        )
        
        logger.info(f"💬 Chat processed for user: {user_id}")
        
        return ChatResponse(
            reply=reply,
            conversation_id=conv_id,
            timestamp=datetime.utcnow()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/conversations")
async def get_conversations(
    current_user: dict = Depends(get_current_active_user)
):
    """Get all conversations for authenticated user"""
    try:
        conversations = list(db.conversations.find(
            {"user_id": current_user["id"]},
            {"_id": 0}
        ).sort("updated_at", -1))
        return {"conversations": conversations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/history/{conversation_id}")
async def get_conversation_history(
    conversation_id: str, 
    current_user: dict = Depends(get_current_active_user)
):
    """Get message history for a specific conversation"""
    try:
        messages = list(db.messages.find(
            {"conversation_id": conversation_id, "user_id": current_user["id"]},
            {"_id": 0}
        ).sort("timestamp", 1))
        return {"messages": messages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str, 
    current_user: dict = Depends(get_current_active_user)
):
    """Delete a conversation and its messages"""
    try:
        db.conversations.delete_one({"id": conversation_id, "user_id": current_user["id"]})
        db.messages.delete_many({"conversation_id": conversation_id, "user_id": current_user["id"]})
        
        # Clear from memory
        conv_key = f"{current_user['id']}:{conversation_id}"
        if conv_key in chatbot.conversations:
            del chatbot.conversations[conv_key]
            
        return {"message": "Conversation deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))