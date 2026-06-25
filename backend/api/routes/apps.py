from typing import List

import httpx
from backend.api.deps import (
    _access_level_to_tier,
    get_current_user,
    get_effective_tier,
    require_role,
    require_tier,
)
from backend.api.schemas.app_status import AppRuntimeStatus
from backend.api.schemas.members import (
    AddMemberRequest,
    InviteMemberRequest,
    MemberRead,
    MyAccessResponse,
)
from backend.argocd.client import get_argocd_client_for_cluster
from backend.core.config import settings
from backend.db.models import Application, AppMember, ClusterConnection, User
from backend.db.session import get_db
from backend.k8s.client import get_k8s_client_for_cluster
from backend.k8s.manifests import sanitize_k8s_name
from backend.services.app_service import AppService
from backend.services.scaffolding_service import ScaffoldingService
from fastapi import APIRouter, Depends, HTTPException, Query
from shared.models import (
    ApplicationCreate,
    ApplicationExternalImportRequest,
    ApplicationOnboardRequest,
    ApplicationResponse,
    ApplicationScaffoldRequest,
    ApplicationUpdate,
    CiStatusUpdate,
    CnpTier,
    PostgreSQLCredentials,
    UserRole,
)
from sqlalchemy import select
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


@router.get("/{app_id}/status", response_model=AppRuntimeStatus)
async def get_app_runtime_status(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Live K8s pods/replicas + ArgoCD sync/health for an application."""
    app_result = await db.execute(select(Application).where(Application.id == app_id))
    app = app_result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")

    if not app.target_cluster_id:
        raise HTTPException(status_code=409, detail="Application has no target cluster configured")

    cluster_result = await db.execute(
        select(ClusterConnection).where(ClusterConnection.id == app.target_cluster_id)
    )
    cluster = cluster_result.scalar_one_or_none()
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster not found")

    payload: dict = {}

    # K8s pods & replicas
    try:
        k8s = get_k8s_client_for_cluster(cluster)
        if k8s.is_configured():
            resource_name = sanitize_k8s_name(app.name)
            payload.update(k8s.get_pods_status(settings.K8S_TARGET_NAMESPACE, resource_name))
    except Exception as e:
        payload["k8s_error"] = str(e)

    # ArgoCD sync / health / image / last sync (dev + prod)
    try:
        argocd = get_argocd_client_for_cluster(cluster)

        async def _fetch_env(name: str) -> dict:
            try:
                data = await argocd.get_app_status(name)
                s = data.get("status", {})
                images = s.get("summary", {}).get("images", [])
                return {
                    "sync_status": s.get("sync", {}).get("status"),
                    "health_status": s.get("health", {}).get("status"),
                    "image": images[0] if images else None,
                    "last_sync_at": s.get("operationState", {}).get("finishedAt"),
                }
            except Exception as exc:
                return {"error": str(exc)}

        dev_data = await _fetch_env(f"{app.slug}-dev")
        prod_data = await _fetch_env(f"{app.slug}-prod")
        payload["argocd_dev"] = dev_data
        payload["argocd_prod"] = prod_data

        # Persist last_known_status: prefer prod health, fallback to dev
        from shared.models import ApplicationStatus
        ref = prod_data if prod_data.get("health_status") else dev_data
        health = ref.get("health_status")
        sync = ref.get("sync_status")
        if health in ("Degraded", "Missing"):
            app.last_known_status = ApplicationStatus.DEGRADED
        elif sync == "Synced" and health == "Healthy":
            app.last_known_status = ApplicationStatus.DEPLOYED
        await db.commit()
    except (HTTPException, httpx.HTTPError) as e:
        payload["argocd_error"] = str(e)
    except Exception as e:
        payload["argocd_error"] = str(e)

    return AppRuntimeStatus(**payload)


@router.get("/{app_id}/members", response_model=List[MemberRead])
async def list_app_members(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_tier(CnpTier.VIEWER)),
):
    result = await db.execute(select(Application).where(Application.id == app_id))
    app = result.scalar_one_or_none()
    if not app or not app.gitlab_project_id:
        return []
    result = await db.execute(
        select(AppMember, User)
        .outerjoin(User, AppMember.cnp_user_id == User.id)
        .where(AppMember.gitlab_project_id == app.gitlab_project_id)
    )
    return [
        MemberRead(
            cnp_user_id=m.cnp_user_id,
            display_name=u.email if u else None,
            access_level=m.access_level,
            tier_cnp=_access_level_to_tier(m.access_level),
            status=m.status,
        )
        for m, u in result.all()
    ]


@router.post("/{app_id}/members", response_model=MemberRead, status_code=201)
async def add_app_member(
    app_id: int,
    payload: AddMemberRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_tier(CnpTier.MAINTAINER)),
):
    """Add a known GitLab user to the app project (write-through mirror)."""
    member = await AppService(db).add_member(app_id, payload.gitlab_user_id, payload.access_level)
    result = await db.execute(select(User).where(User.id == member.cnp_user_id)) if member.cnp_user_id else None
    cnp_user = result.scalar_one_or_none() if result else None
    return MemberRead(
        cnp_user_id=member.cnp_user_id,
        display_name=cnp_user.email if cnp_user else None,
        access_level=member.access_level,
        tier_cnp=_access_level_to_tier(member.access_level),
        status=member.status,
    )


@router.post("/{app_id}/invitations", response_model=MemberRead, status_code=201)
async def invite_app_member(
    app_id: int,
    payload: InviteMemberRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_tier(CnpTier.MAINTAINER)),
):
    """Invite a user by email to the app project (write-through mirror)."""
    member = await AppService(db).invite_member(app_id, payload.email, payload.access_level)
    return MemberRead(
        cnp_user_id=None,
        display_name=payload.email,
        access_level=member.access_level,
        tier_cnp=_access_level_to_tier(member.access_level),
        status=member.status,
    )


@router.get("/{app_id}/my-access", response_model=MyAccessResponse)
async def get_my_access(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tier = await get_effective_tier(current_user.id, app_id, db)
    return MyAccessResponse(tier=tier, is_admin=current_user.is_admin)


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


@router.get("/{app_id}/services/postgresql/credentials", response_model=PostgreSQLCredentials)
async def get_postgresql_credentials(
    app_id: int,
    namespace: str = Query(..., description="Kubernetes namespace where the app is deployed"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_tier(CnpTier.MAINTAINER)),
):
    """Read PostgreSQL credentials from the K8s Secret created by the Bitnami subchart."""
    return await AppService(db).get_postgresql_credentials(app_id, namespace)


@router.put("/{app_id}", response_model=ApplicationResponse)
async def update_app(
    app_id: int,
    payload: ApplicationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    return await AppService(db).update_app(app_id, payload)


@router.post("/{app_id}/ci-status", response_model=ApplicationResponse)
async def update_app_ci_status(
    app_id: int,
    payload: CiStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    """CI runner callback: update pipeline status on an application."""
    return await AppService(db).update_ci_status(app_id, payload)


@router.delete("/{app_id}")
async def delete_app(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.DEV)),
):
    await AppService(db).delete_app(app_id)
    return {"msg": "Application deleted"}
