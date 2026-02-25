from datetime import datetime, timedelta, timezone
from typing import Optional
import os

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel


SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY must be set in environment variables")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

security = HTTPBearer()


class TokenData(BaseModel):
    user_id: Optional[str] = None
    email: Optional[str] = None


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    )

    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    })

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id: str = payload.get("sub")

        if not user_id:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    from app.db import db

    user = db.users.find_one({"id": user_id})

    if not user:
        raise credentials_exception

    return user


def get_current_active_user(
    current_user: dict = Depends(get_current_user)
):
    if not current_user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user
