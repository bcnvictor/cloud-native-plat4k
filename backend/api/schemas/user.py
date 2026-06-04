"""
User related schemas.
"""
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
