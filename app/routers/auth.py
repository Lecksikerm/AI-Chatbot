from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime
import uuid

from app.models import UserRegister, UserLogin, GoogleAuth, Token, UserResponse
from app.auth import (
    get_password_hash, verify_password, create_access_token, 
    get_current_active_user
)
from app.google_auth import verify_google_token
from app.db import db

router = APIRouter(prefix="/auth", tags=["authentication"])

@router.post("/register", response_model=Token)
async def register(user_data: UserRegister):
    """Register new user with email/password"""
    # Check if user exists
    if db.users.find_one({"email": user_data.email}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create user
    user_id = str(uuid.uuid4())
    user_doc = {
        "id": user_id,
        "email": user_data.email,
        "password": get_password_hash(user_data.password),
        "name": user_data.name,
        "avatar": None,
        "google_id": None,
        "role": "free",
        "message_count": 0,
        "message_limit": 100,
        "is_active": True,
        "is_email_verified": False,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    db.users.insert_one(user_doc)
    
    # Generate token
    access_token = create_access_token(data={"sub": user_id, "email": user_data.email})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user_id,
            "email": user_data.email,
            "name": user_data.name,
            "role": "free",
            "message_count": 0,
            "message_limit": 100
        }
    }

@router.post("/login", response_model=Token)
async def login(credentials: UserLogin):
    """Login with email/password"""
    user = db.users.find_one({"email": credentials.email})
    
    if not user or not verify_password(credentials.password, user.get("password", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    access_token = create_access_token(
        data={"sub": user["id"], "email": user["email"]}
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "avatar": user.get("avatar"),
            "role": user.get("role", "free"),
            "message_count": user.get("message_count", 0),
            "message_limit": user.get("message_limit", 100)
        }
    }

@router.post("/google", response_model=Token)
async def google_auth(auth_data: GoogleAuth):
    """Login/Register with Google"""
    # Verify Google token
    google_user = await verify_google_token(auth_data.token)
    
    # Check if user exists by Google ID
    user = db.users.find_one({"google_id": google_user["google_id"]})
    
    if not user:
        # Check if email exists (link accounts)
        user = db.users.find_one({"email": google_user["email"]})
        
        if user:
            # Link Google to existing account
            db.users.update_one(
                {"id": user["id"]},
                {"$set": {
                    "google_id": google_user["google_id"],
                    "avatar": google_user.get("avatar") or user.get("avatar"),
                    "is_email_verified": google_user.get("email_verified", False),
                    "updated_at": datetime.utcnow()
                }}
            )
        else:
            # Create new user
            user_id = str(uuid.uuid4())
            user = {
                "id": user_id,
                "email": google_user["email"],
                "password": None,  # No password for OAuth users
                "name": google_user["name"],
                "avatar": google_user.get("avatar"),
                "google_id": google_user["google_id"],
                "role": "free",
                "message_count": 0,
                "message_limit": 100,
                "is_active": True,
                "is_email_verified": google_user.get("email_verified", False),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            db.users.insert_one(user)
    
    access_token = create_access_token(
        data={"sub": user["id"], "email": user["email"]}
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "avatar": user.get("avatar"),
            "role": user.get("role", "free"),
            "message_count": user.get("message_count", 0),
            "message_limit": user.get("message_limit", 100)
        }
    }

@router.get("/me", response_model=dict)
async def get_me(current_user: dict = Depends(get_current_active_user)):
    """Get current user profile"""
    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "name": current_user["name"],
        "avatar": current_user.get("avatar"),
        "role": current_user.get("role", "free"),
        "message_count": current_user.get("message_count", 0),
        "message_limit": current_user.get("message_limit", 100),
        "created_at": current_user["created_at"]
    }