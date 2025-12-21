from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from ..database import get_db
from ..crud import get_user_by_username
from ..schemas import UserOut, Token, ChangePassword
from ..auth import verify_password, create_access_token, get_current_user, get_password_hash
from ..models import User

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/register", response_model=UserOut)
def register(
    username: str = Form(..., description="**Unique username**", examples=[""]),
    email: str = Form(..., description="**Valid email address**", examples=[""]),
    password: str = Form(..., min_length=8, description="**Password (minimum 8 characters, English only)**", examples=[""]),
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
    
  
    try:
        is_admin = getattr(new_user, 'is_admin', False)
        setattr(new_user, 'is_admin', is_admin)
    except (AttributeError, KeyError):
        setattr(new_user, 'is_admin', False)

    return UserOut.model_validate(new_user)


@router.post("/login", response_model=Token)
def login(
    username: str = Form(..., description="**Username you chose during registration**",  examples=[""]),
    password: str = Form(..., min_length=8, description="**Password (minimum 8 characters)**",  examples=[""]),
    db: Session = Depends(get_db)
):
    
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

@router.patch("/me", response_model=UserOut)
def update_profile(
    username: Optional[str] = Form(None, description="**New username** (optional, must be unique if changed)", examples=[""]),
    email: Optional[str] = Form(None, description="**New email address** (optional, must be valid)", examples=[""]),
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db)
):
   
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


@router.patch("/change-password", response_model=UserOut)
def change_password(
    current_password: str = Form(..., description="**Current password** (required for verification)", examples=[""]),
    new_password: str = Form(..., min_length=8, description="**New password** (minimum 8 characters, English only)", examples=[""]),
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    
    # Retrieve the actual user from the database
    user = get_user_by_username(db, username=current_user.username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect"
        )

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

# Delete Account (with current password verification)
@router.delete("/delete-account", response_model=UserOut)
def delete_account(
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db)
):
   
    user = get_user_by_username(db, username=current_user.username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Store user data for response before deletion
    user_data = UserOut.model_validate(user)
    
    db.delete(user)
    db.commit()
    
    return user_data