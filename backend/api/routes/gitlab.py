import json
import base64
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.api.deps import get_current_user
from backend.core.config import settings
from backend.db.models import GitLabCredential, User
from backend.db.session import get_db
from backend.gitlab.client import GitLabClient

router = APIRouter()

GITLAB_BASE_URL = "https://gitlab.cri.epita.fr"
PAT_URL = f"{GITLAB_BASE_URL}/-/user_settings/personal_access_tokens"


def _fernet() -> Fernet:
    if settings.ENCRYPTION_KEY:
        return Fernet(settings.ENCRYPTION_KEY.encode())
    key = base64.urlsafe_b64encode(settings.SECRET_KEY.encode()[:32].ljust(32, b"0"))
    return Fernet(key)


def _encrypt(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def _decrypt(encrypted: str) -> str:
    return _fernet().decrypt(encrypted.encode()).decode()


async def _get_user_gitlab_cred(user_id: int, db: AsyncSession) -> GitLabCredential | None:
    result = await db.execute(
        select(GitLabCredential).where(GitLabCredential.user_id == user_id)
    )
    return result.scalar_one_or_none()


# ── Schemas ───────────────────────────────────────────────────────────────────

class GitLabCredentialCreate(BaseModel):
    token: str
    namespace: str


class GitLabCredentialResponse(BaseModel):
    namespace: str
    configured: bool

    class Config:
        from_attributes = True


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/setup-guide")
async def gitlab_setup_guide(current_user: User = Depends(get_current_user)):
    """Retourne le lien et les instructions pour créer un PAT sur gitlab.cri.epita.fr."""
    return {
        "pat_url": PAT_URL,
        "required_scopes": ["api", "write_repository"],
        "note": "Le token commence par 'glpat-'. Il ne sera affiché qu'une seule fois.",
    }


@router.get("/credentials", response_model=GitLabCredentialResponse)
async def get_gitlab_credentials(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retourne les infos GitLab configurées pour l'utilisateur courant (sans le token)."""
    cred = await _get_user_gitlab_cred(current_user.id, db)
    if not cred:
        return {"namespace": "", "configured": False}
    return {"namespace": cred.namespace, "configured": True}


@router.post("/credentials", response_model=GitLabCredentialResponse)
async def save_gitlab_credentials(
    payload: GitLabCredentialCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sauvegarde (ou met à jour) le PAT GitLab et le namespace de l'utilisateur."""
    if not payload.token.strip():
        raise HTTPException(status_code=422, detail="token cannot be empty")
    if not payload.namespace.strip():
        raise HTTPException(status_code=422, detail="namespace cannot be empty")

    encrypted = _encrypt(payload.token.strip())
    cred = await _get_user_gitlab_cred(current_user.id, db)

    if cred:
        cred.encrypted_token = encrypted
        cred.namespace = payload.namespace.strip()
    else:
        cred = GitLabCredential(
            user_id=current_user.id,
            encrypted_token=encrypted,
            namespace=payload.namespace.strip(),
        )
        db.add(cred)

    await db.commit()
    await db.refresh(cred)
    return {"namespace": cred.namespace, "configured": True}


@router.delete("/credentials")
async def delete_gitlab_credentials(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Supprime les credentials GitLab de l'utilisateur."""
    cred = await _get_user_gitlab_cred(current_user.id, db)
    if cred:
        await db.delete(cred)
        await db.commit()
    return {"msg": "GitLab credentials deleted"}


@router.get("/healthcheck")
async def gitlab_healthcheck(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Vérifie la connexion GitLab via le PAT stocké en DB pour l'utilisateur courant."""
    cred = await _get_user_gitlab_cred(current_user.id, db)
    if not cred:
        return {
            "status": "not_configured",
            "detail": "Aucun token GitLab configuré. Renseignez votre PAT dans la section Credentials.",
        }
    try:
        token = _decrypt(cred.encrypted_token)
    except Exception:
        return {"status": "error", "detail": "Impossible de déchiffrer le token stocké."}

    client = GitLabClient(token=token, namespace=cred.namespace)
    return client.healthcheck()
