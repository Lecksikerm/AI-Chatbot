import os
import httpx
from fastapi import HTTPException

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

async def verify_google_token(token: str):
    """Verify Google ID token and return user info"""
    try:
        async with httpx.AsyncClient() as client:
            # Verify token with Google
            response = await client.get(
                f"https://oauth2.googleapis.com/tokeninfo?id_token={token}"
            )
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Invalid Google token")
            
            payload = response.json()
            
            # Verify client ID
            if payload.get("aud") != GOOGLE_CLIENT_ID:
                raise HTTPException(status_code=400, detail="Invalid token audience")
            
            # Check expiration
            if payload.get("exp") and int(payload["exp"]) < __import__('time').time():
                raise HTTPException(status_code=400, detail="Token expired")
            
            return {
                "email": payload["email"],
                "name": payload.get("name", payload["email"].split("@")[0]),
                "google_id": payload["sub"],
                "avatar": payload.get("picture"),
                "email_verified": payload.get("email_verified", False)
            }
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Could not verify with Google")