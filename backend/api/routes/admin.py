from backend.api.deps import require_admin
from backend.db.models import User
from backend.db.session import get_db
from backend.services.gitlab_sync_service import run_gitlab_sync
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post("/sync-gitlab")
async def trigger_gitlab_sync(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Déclenche manuellement un cycle complet de réconciliation GitLab (is_admin requis)."""
    return await run_gitlab_sync(db)
