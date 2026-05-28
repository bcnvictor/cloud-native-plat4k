"""
Auth related schemas.
"""
from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str

class TokenPayload(BaseModel):
    sub: str = None

class LoginPayload(BaseModel):
    email: str
    password: str


class RefreshTokenPayload(BaseModel):
    refresh_token: str
