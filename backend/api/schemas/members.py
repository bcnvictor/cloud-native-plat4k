from datetime import datetime
from typing import Optional

from pydantic import BaseModel
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
