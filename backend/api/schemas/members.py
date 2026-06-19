from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from shared.models import CnpTier, MemberStatus


class MemberRead(BaseModel):
    cnp_user_id: Optional[int] = None
    display_name: Optional[str] = None
    access_level: int
    tier_cnp: CnpTier
    status: MemberStatus

    class Config:
        from_attributes = True


class GroupRead(BaseModel):
    gitlab_group_id: int
    name: str
    full_path: str
    synced_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MyAccessResponse(BaseModel):
    tier: CnpTier
    is_admin: bool


class GroupMembershipRead(BaseModel):
    gitlab_group_id: int
    name: str
    full_path: str
    access_level: int
    tier_cnp: CnpTier
    status: MemberStatus


class AddMemberRequest(BaseModel):
    gitlab_user_id: int
    access_level: int = Field(default=30, ge=10, le=40)


class InviteMemberRequest(BaseModel):
    email: str
    access_level: int = Field(default=30, ge=10, le=40)
