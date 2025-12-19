from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from ..database import get_db
from ..crud import get_user_by_username, get_all_users, delete_user, get_user_by_id
from ..schemas import UserOut, Token
from ..auth import verify_password, create_access_token, get_current_admin, get_password_hash
from ..models import User

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/login", response_model=Token)
def admin_login(
    username: str = Form(..., description="**Admin username**", examples=["admin"]),
    password: str = Form(..., description="**Admin password**", examples=["admin"]),
    db: Session = Depends(get_db)
):
    """
    Admin login endpoint
    """
    user = get_user_by_username(db, username=username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user is admin - safely handle if column doesn't exist
    # get_user_by_username already ensures is_admin field exists, but we double-check
    try:
        is_admin = getattr(user, 'is_admin', False)
        # Also check username for admin user
        if user.username == 'admin' and not is_admin:
            is_admin = True
            setattr(user, 'is_admin', True)
    except (AttributeError, KeyError):
        # Column doesn't exist, check username
        is_admin = (user.username == 'admin')
        setattr(user, 'is_admin', is_admin)
    
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin privileges required."
        )
    
    # Verify password
    if not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/users", response_model=List[UserOut])
def list_all_users(
    skip: int = 0,
    limit: int = 100,
    current_admin: UserOut = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Get list of all users (Admin only)
    """
    users = get_all_users(db, skip=skip, limit=limit)
    return [UserOut.model_validate(user) for user in users]


@router.delete("/users/{user_id}", response_model=UserOut)
def delete_user_by_admin(
    user_id: int,
    current_admin: UserOut = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Delete a user by ID (Admin only)
    """
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Prevent admin from deleting themselves
    if user.id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    user_data = UserOut.model_validate(user)
    delete_user(db, user_id)
    return user_data

