"""
User related schemas.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from shared.models import UserBase, UserRole


class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None

class UserMeResponse(BaseModel):
    id: int
    email: str
    role: UserRole
    is_active: bool
    is_admin: bool
    gitlab_user_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True
