from sqlalchemy.orm import Session
from .models import User
from .schemas import UserCreate
from typing import List, Optional

def _ensure_is_admin_field(user: Optional[User]) -> Optional[User]:
    """
    Helper function to ensure is_admin field has correct value.
    Ensures admin user always has is_admin=True.
    """
    if user is None:
        return None
    
    # Ensure admin user always has is_admin=True
    if user.username == 'admin' and not user.is_admin:
        user.is_admin = True
    
    return user

def create_user(db: Session, user: UserCreate):
    from .auth import get_password_hash

    hashed_password = get_password_hash(user.password)
    # Create user with is_admin=False by default (handled by database default)
    db_user = User(username=user.username, email=user.email, hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return _ensure_is_admin_field(db_user)

def get_user_by_username(db: Session, username: str):
    """
    Get user by username, ensuring is_admin field is set correctly.
    """
    user = db.query(User).filter(User.username == username).first()
    return _ensure_is_admin_field(user)

def get_all_users(db: Session, skip: int = 0, limit: int = 100) -> List[User]:
    """
    Get all users, ensuring is_admin field is set correctly for each.
    """
    users = db.query(User).offset(skip).limit(limit).all()
    return [_ensure_is_admin_field(user) for user in users if user is not None]

def get_user_by_id(db: Session, user_id: int):
    """
    Get user by ID, ensuring is_admin field is set correctly.
    """
    user = db.query(User).filter(User.id == user_id).first()
    return _ensure_is_admin_field(user)

def delete_user(db: Session, user_id: int):
    user = get_user_by_id(db, user_id)
    if user:
        db.delete(user)
        db.commit()
        return True
    return False