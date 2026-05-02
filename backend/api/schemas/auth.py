"""
Auth related schemas.
"""
from pydantic import BaseModel, EmailStr

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenPayload(BaseModel):
    sub: str = None

class LoginPayload(BaseModel):
    email: EmailStr
    password: str
