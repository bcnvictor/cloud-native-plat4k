from typing import List

from backend.api.deps import get_current_user, require_role
from backend.db.models import User
from backend.db.session import get_db
from backend.services.app_service import AppService
from backend.services.scaffolding_service import ScaffoldingService
from fastapi import APIRouter, Depends
from shared.models import (
    ApplicationCreate,
    ApplicationExternalImportRequest,
    ApplicationOnboardRequest,
    ApplicationResponse,
    ApplicationScaffoldRequest,
    ApplicationUpdate,
    UserRole,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/templates", response_model=List[dict])
async def list_templates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List available templates from GITLAB_TEMPLATES_NAMESPACE."""
    return await ScaffoldingService(db).list_templates()


@router.get("/", response_model=List[ApplicationResponse])
async def list_apps(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await AppService(db).list_apps()


@router.get("/{app_id}", response_model=ApplicationResponse)
async def get_app(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await AppService(db).get_app(app_id)


@router.post("/scaffold", response_model=ApplicationResponse, status_code=201)
async def scaffold_app(
    payload: ApplicationScaffoldRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.DEV)),
):
    """Create a new app from a CNP template (scaffolding)."""
    return await AppService(db).scaffold_app(payload)


@router.post("/onboard", response_model=ApplicationResponse, status_code=201)
async def onboard_app(
    payload: ApplicationOnboardRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.DEV)),
):
    """Register an existing internal GitLab repo as a CNP app (onboard)."""
    return await AppService(db).onboard_app(payload)


@router.post("/import", response_model=ApplicationResponse, status_code=201)
async def import_app(
    payload: ApplicationExternalImportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.DEV)),
):
    """Clone a public external repo (GitHub/GitLab) into cnp-apps and register it."""
    return await AppService(db).external_import_app(payload)


@router.post("/sync", response_model=List[ApplicationResponse])
async def sync_apps_from_k8s(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Discover K8s Deployments in the configured namespace and import them into the database."""
    return await AppService(db).sync_from_k8s()


@router.post("/", response_model=ApplicationResponse, status_code=201)
async def create_app(
    payload: ApplicationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Register an app directly (no scaffold, no repo validation)."""
    return await AppService(db).create_app(payload)


@router.put("/{app_id}", response_model=ApplicationResponse)
async def update_app(
    app_id: int,
    payload: ApplicationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    return await AppService(db).update_app(app_id, payload)


@router.delete("/{app_id}")
async def delete_app(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    await AppService(db).delete_app(app_id)
    return {"msg": "Application deleted"}
