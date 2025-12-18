from pydantic import BaseModel, ConfigDict, EmailStr, Field

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72)

class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr

    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str

from pydantic import BaseModel, Field

class LoginRequest(BaseModel):
    username: str = Field(..., description="The username you chose during registration")
    password: str = Field(..., min_length=8, description="Password (minimum 8 characters, English only)")

    model_config = ConfigDict(from_attributes=True)
class ChangePassword(BaseModel):
    current_password: str = Field(..., min_length=8, description="**Current password** (to verify identity)")
    new_password: str = Field(..., min_length=8, description="**New password** (minimum 8 characters, English only)")