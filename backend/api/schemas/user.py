"""
User related schemas.
"""
from shared.models import UserBase, UserResponse, UserRole
from pydantic import BaseModel, EmailStr
from typing import Optional

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None
