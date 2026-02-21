from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import uuid
from datetime import datetime

from app.models import ChatRequest, ChatResponse 
from app.chatbot import chatbot
from app.db import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 AI SaaS Backend starting...")
    yield
    logger.info("🛑 AI SaaS Backend shutting down...")

app = FastAPI(
    title="AI SaaS API",
    description="ChatGPT-style AI SaaS powered by Gemini",
    version="1.0.0",
    lifespan=lifespan
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "https://ai-saas-frontend.vercel.app",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "message": "AI SaaS API is running! 🤖",
        "docs": "/docs",
        "health": "/health",
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    try:
        db.client.admin.command('ping')
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Chat endpoint with MEMORY"""
    try:
        conv_id = req.conversation_id or str(uuid.uuid4())
        
        # Load history
        history = []
        if req.use_memory:
            history = list(db.messages.find(
                {"conversation_id": conv_id, "user_id": req.user_id},
                {"_id": 0, "user_message": 1, "bot_reply": 1}
            ).sort("timestamp", 1))
            logger.info(f"🧠 Loaded {len(history)} messages from history")
        
        # Get AI response
        reply = chatbot.ask_ai(
            message=req.message,
            user_id=req.user_id,
            conversation_id=conv_id,
            history=history if req.use_memory else None
        )
        
        # Store in MongoDB
        message_doc = {
            "user_id": req.user_id,
            "conversation_id": conv_id,
            "user_message": req.message,
            "bot_reply": reply,
            "timestamp": datetime.utcnow(),
            "model": "gemini-1.5-flash"
        }
        db.messages.insert_one(message_doc)
        
        # Update conversation metadata
        db.conversations.update_one(
            {"id": conv_id, "user_id": req.user_id},
            {
                "$set": {
                    "user_id": req.user_id,
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
        
        logger.info(f"💬 Chat processed for user: {req.user_id}")
        
        return ChatResponse(
            reply=reply,
            conversation_id=conv_id,
            timestamp=datetime.utcnow()
        )
        
    except Exception as e:
        logger.error(f"❌ Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/conversations/{user_id}")
async def get_conversations(user_id: str):
    """Get all conversations for a user"""
    try:
        conversations = list(db.conversations.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("updated_at", -1))
        return {"conversations": conversations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/history/{conversation_id}")
async def get_conversation_history(conversation_id: str, user_id: str):
    """Get message history for a specific conversation"""
    try:
        messages = list(db.messages.find(
            {"conversation_id": conversation_id, "user_id": user_id},
            {"_id": 0}
        ).sort("timestamp", 1))
        return {"messages": messages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, user_id: str):
    """Delete a conversation and its messages"""
    try:
        db.conversations.delete_one({"id": conversation_id, "user_id": user_id})
        db.messages.delete_many({"conversation_id": conversation_id, "user_id": user_id})
        
        # Clear from memory
        conv_key = f"{user_id}:{conversation_id}"
        if conv_key in chatbot.conversations:
            del chatbot.conversations[conv_key]
            
        return {"message": "Conversation deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))