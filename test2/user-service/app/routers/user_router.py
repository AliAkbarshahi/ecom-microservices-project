from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..crud import get_user_by_username
from ..schemas import UserOut, Token, ChangePassword
from ..auth import verify_password, create_access_token, get_current_user, get_password_hash
from ..models import User
from fastapi import Form
router = APIRouter(prefix="/users", tags=["users"])

from fastapi import Form

@router.post("/register", response_model=UserOut)
def register(
    username: str = Form(..., description="**Unique username**"),
    email: str = Form(..., description="**Valid email address**"),
    password: str = Form(..., min_length=8, description="**Password (minimum 8 characters, English only)**"),
    db: Session = Depends(get_db)
):
    # Check password byte length (bcrypt limitation)
    if len(password.encode('utf-8')) > 72:
        raise HTTPException(
            status_code=400,
            detail="Password is too long or contains non-English characters (e.g., Persian). Please use only English letters and numbers."
        )

    # Check if username already exists
    db_user = get_user_by_username(db, username=username)
    if db_user:
        raise HTTPException(status_code=400, detail="This username is already registered")

    # Create new user
    hashed_password = get_password_hash(password)
    new_user = User(username=username, email=email, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user  # or UserOut.from_attributes(new_user)

from fastapi import Form

@router.post("/login", response_model=Token)
def login(
    username: str = Form(..., description="**Username you chose during registration**"),
    password: str = Form(..., min_length=8, description="**Password (minimum 8 characters)**"),
    db: Session = Depends(get_db)
):
    """
    User login endpoint
    """
    user = get_user_by_username(db, username=username)
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/my profile", response_model=UserOut)
def read_users_me(current_user: UserOut = Depends(get_current_user)):
    return current_user

# New Endpoint: Update Profile
@router.patch("/me", response_model=UserOut)
def update_profile(
    username: Optional[str] = Form(None, description="**New username** (optional, must be unique if changed)"),
    email: Optional[str] = Form(None, description="**New email address** (optional, must be valid)"),
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update current user's profile
    """
    # Get the actual user model from DB
    user = get_user_by_username(db, username=current_user.username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update username if provided
    if username is not None and username != "":
        if username != user.username:  # Only check if changed
            db_user = get_user_by_username(db, username=username)
            if db_user:
                raise HTTPException(status_code=400, detail="This username is already registered")
            user.username = username

    # Update email if provided
    if email is not None and email != "":
        user.email = email

    # Save changes
    db.commit()
    db.refresh(user)

    return UserOut.model_validate(user)


# --- PATCH /change-password ---
@router.patch("/change-password", response_model=UserOut)
def change_password(
    current_password: str = Form(..., description="**Current password** (required for verification)"),
    new_password: str = Form(..., min_length=8, description="**New password** (minimum 8 characters, English only)"),
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Change current user's password (requires current password verification)
    """
    # Retrieve the actual user from the database
    user = get_user_by_username(db, username=current_user.username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify current password (high security!)
    if not verify_password(current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect"
        )

    # Check byte length of new password (for bcrypt compatibility)
    if len(new_password.encode('utf-8')) > 72:
        raise HTTPException(
            status_code=400,
            detail="New password is too long or contains non-English characters. Use only English letters and numbers."
        )

    # Hash the new password and save it
    user.hashed_password = get_password_hash(new_password)

    db.commit()
    db.refresh(user)

    return UserOut.model_validate(user)