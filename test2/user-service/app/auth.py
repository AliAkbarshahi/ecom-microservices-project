from sqlalchemy.orm import Session
from .database import get_db
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from dotenv import load_dotenv
import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
from datetime import datetime, timedelta, timezone
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "8f3b9e7a2c4d1f5e6a8b0c9d3e7f2a1b4c6d8e9f0a5b7c2d1e3f4a6b8c9d0e1f2")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt", "argon2"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

oauth2_scheme = HTTPBearer()

async def get_current_user(credentials: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    from sqlalchemy.orm import Session
    from .database import get_db
    from .crud import get_user_by_username
    from .schemas import UserOut

    db: Session = next(get_db())  
    user = get_user_by_username(db, username=username)
    if user is None:
        raise credentials_exception
    
    return UserOut.model_validate(user)