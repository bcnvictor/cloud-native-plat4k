from typing import List

from backend.api.deps import get_current_user
from backend.db.models import CloudCredential, User
from backend.db.session import get_db
from backend.services.credential_service import CredentialService
from fastapi import APIRouter, Depends, Request
from shared.models import CredentialCreate, CredentialResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

@router.get("/", response_model=List[CredentialResponse])
async def list_credentials(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(CloudCredential).where(CloudCredential.user_id == current_user.id))
    return result.scalars().all()

@router.post("/", response_model=CredentialResponse)
async def add_credential(
    payload: CredentialCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = CredentialService(db)
    return await service.add_credentials(current_user.id, payload)

@router.delete("/{credential_id}")
async def delete_credential(
    credential_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(CloudCredential).where(CloudCredential.id == credential_id, CloudCredential.user_id == current_user.id))
    cred = result.scalar_one_or_none()
    if cred:
        await db.delete(cred)
        await db.commit()
    return {"msg": "Credential deleted"}
