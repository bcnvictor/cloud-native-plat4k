import hmac
from typing import List

import httpx
import yaml
from backend.alerting.constants import EventType
from backend.alerting.emitter import emit_event
from backend.api.deps import (
    _access_level_to_tier,
    get_current_user,
    get_effective_tier,
    require_role,
    require_tier,
)
from backend.api.schemas.app_status import (
    AppRuntimeStatus,
    AppScaleStateItem,
    AppScaleStateResponse,
)
from backend.api.schemas.members import (
    AddMemberRequest,
    InviteMemberRequest,
    MemberRead,
    MyAccessResponse,
)
from backend.argocd.client import get_argocd_client_for_cluster
from backend.ci.detector import extract_project_path
from backend.core.config import settings
from backend.db.models import Application, AppMember, ClusterConnection, User
from backend.db.session import get_db
from backend.gitlab.client import GitLabClient
from backend.k8s.client import get_k8s_client_for_cluster
from backend.k8s.manifests import sanitize_k8s_name
from backend.services.app_service import AppService
from backend.services.audit_service import AuditService
from backend.services.scaffolding_service import ScaffoldingService
from backend.services.scale_service import ScaleService
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
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

    # K8s pods & replicas — try prod then dev namespace (platform convention)
    try:
        k8s = get_k8s_client_for_cluster(cluster)
        if k8s.is_configured():
            resource_name = sanitize_k8s_name(app.name)
            for ns in ("prod", "dev", settings.K8S_TARGET_NAMESPACE):
                try:
                    payload.update(k8s.get_pods_status(ns, resource_name))
                    break
                except Exception:
                    continue
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
        old_status = app.last_known_status
        if health in ("Degraded", "Missing"):
            app.last_known_status = ApplicationStatus.DEGRADED
            if old_status != ApplicationStatus.DEGRADED:
                await emit_event(db, EventType.APP_HEALTH_DEGRADED, "critical", "argocd",
                                 app_id=app.id, payload={"name": app.name, "health": health})
        elif sync == "Synced" and health == "Healthy":
            app.last_known_status = ApplicationStatus.DEPLOYED
            if old_status == ApplicationStatus.DEGRADED:
                await emit_event(db, EventType.APP_HEALTH_RECOVERED, "info", "argocd",
                                 app_id=app.id, payload={"name": app.name})
        await db.commit()
    except (HTTPException, httpx.HTTPError) as e:
        payload["argocd_error"] = str(e)
    except Exception as e:
        payload["argocd_error"] = str(e)

    return AppRuntimeStatus(**payload)


@router.get("/{app_id}/history")
async def get_app_history(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_tier(CnpTier.VIEWER)),
):
    """Return ArgoCD deployment history for dev and prod environments."""
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

    argocd = get_argocd_client_for_cluster(cluster)
    result: dict[str, list] = {}
    for env in ("dev", "prod"):
        try:
            result[env] = await argocd.get_app_history(f"{app.slug}-{env}")
        except Exception:
            result[env] = []
    return result


class RollbackRequest(BaseModel):
    history_id: int
    env: str  # "dev" or "prod"


@router.post("/{app_id}/rollback", status_code=200)
async def rollback_app(
    app_id: int,
    payload: RollbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tier(CnpTier.MAINTAINER)),
):
    """Roll back an ArgoCD application to a previous history entry (Maintainer+)."""
    app_result = await db.execute(select(Application).where(Application.id == app_id))
    app = app_result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    if not app.target_cluster_id:
        raise HTTPException(status_code=409, detail="Application has no target cluster configured")
    if payload.env not in ("dev", "prod"):
        raise HTTPException(status_code=422, detail="env must be 'dev' or 'prod'")

    cluster_result = await db.execute(
        select(ClusterConnection).where(ClusterConnection.id == app.target_cluster_id)
    )
    cluster = cluster_result.scalar_one_or_none()
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster not found")

    argocd = get_argocd_client_for_cluster(cluster)
    history = await argocd.get_app_history(f"{app.slug}-{payload.env}")
    entry = next((e for e in history if e.get("id") == payload.history_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail="History entry not found")
    old_tag = ((entry.get("revisions") or [None])[0] or "")[:8] or None
    if not old_tag:
        raise HTTPException(status_code=409, detail="Cannot determine image tag for this history entry")

    if not settings.GITOPS_REPO_URL or not settings.GITLAB_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="GitOps not configured (missing GITOPS_REPO_URL or GITLAB_BOT_TOKEN)")

    gitops_project = extract_project_path(settings.GITOPS_REPO_URL)
    values_path = f"apps/{cluster.name}/{app.slug}/values-{payload.env}.yaml"
    gl = GitLabClient(token=settings.GITLAB_BOT_TOKEN, namespace="", use_private_token=True)

    raw = gl.read_file(gitops_project, values_path)
    data = yaml.safe_load(raw)
    data["image"]["tag"] = old_tag
    new_content = yaml.dump(data, default_flow_style=False, allow_unicode=True)
    gl.push_file(gitops_project, values_path, new_content, f"chore: rollback {app.slug}-{payload.env} to {old_tag}")

    audit = AuditService(db)
    await audit.log_action(
        current_user.id,
        f"rollback:{payload.env}:{payload.history_id}",
        app_id=app_id,
        extra={"env": payload.env, "history_id": payload.history_id},
    )
    await emit_event(db, EventType.APP_ROLLBACK, "warning", "argocd",
                     app_id=app_id,
                     payload={"name": app.name, "env": payload.env, "history_id": payload.history_id},
                     actor_user_id=current_user.id)
    await db.commit()

    return {"ok": True}


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
    app = await AppService(db).scaffold_app(payload)
    audit = AuditService(db)
    await audit.log_action(current_user.id, "app.created", app_id=app.id,
                           extra={"name": app.name, "origin": app.origin})
    await emit_event(db, EventType.APP_CREATED, "info", "app_service",
                     app_id=app.id, payload={"name": app.name, "origin": app.origin},
                     actor_user_id=current_user.id)
    await db.commit()
    return app


@router.post("/onboard", response_model=ApplicationResponse, status_code=201)
async def onboard_app(
    payload: ApplicationOnboardRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.DEV)),
):
    """Register an existing internal GitLab repo as a CNP app (onboard)."""
    app = await AppService(db).onboard_app(payload)
    audit = AuditService(db)
    await audit.log_action(current_user.id, "app.created", app_id=app.id,
                           extra={"name": app.name, "origin": app.origin})
    await emit_event(db, EventType.APP_CREATED, "info", "app_service",
                     app_id=app.id, payload={"name": app.name, "origin": app.origin},
                     actor_user_id=current_user.id)
    await db.commit()
    return app


@router.post("/import", response_model=ApplicationResponse, status_code=201)
async def import_app(
    payload: ApplicationExternalImportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.DEV)),
):
    """Clone a public external repo (GitHub/GitLab) into cnp-apps and register it."""
    app = await AppService(db).external_import_app(payload)
    audit = AuditService(db)
    await audit.log_action(current_user.id, "app.created", app_id=app.id,
                           extra={"name": app.name, "origin": app.origin})
    await emit_event(db, EventType.APP_CREATED, "info", "app_service",
                     app_id=app.id, payload={"name": app.name, "origin": app.origin},
                     actor_user_id=current_user.id)
    await db.commit()
    return app


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
    app = await AppService(db).create_app(payload)
    audit = AuditService(db)
    await audit.log_action(current_user.id, "app.created", app_id=app.id,
                           extra={"name": app.name, "origin": app.origin})
    await emit_event(db, EventType.APP_CREATED, "info", "app_service",
                     app_id=app.id, payload={"name": app.name, "origin": app.origin},
                     actor_user_id=current_user.id)
    await db.commit()
    return app


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
    app = await AppService(db).update_app(app_id, payload)
    changed = list(payload.model_dump(exclude_unset=True).keys())
    audit = AuditService(db)
    await audit.log_action(current_user.id, "app.updated", app_id=app.id,
                           extra={"name": app.name, "changed": changed})
    await emit_event(db, EventType.APP_UPDATED, "info", "app_service",
                     app_id=app.id, payload={"name": app.name, "changed": changed},
                     actor_user_id=current_user.id)
    await db.commit()
    return app


async def _verify_ci_callback_token(x_cnp_callback_token: str | None = Header(default=None)) -> None:
    """Valide le token partagé injecté comme variable CI (voir ADR-0011)."""
    if not settings.CNP_CALLBACK_TOKEN:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                             detail="CNP_CALLBACK_TOKEN not configured")
    if not x_cnp_callback_token or not hmac.compare_digest(x_cnp_callback_token, settings.CNP_CALLBACK_TOKEN):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing X-CNP-Callback-Token")


@router.post("/{app_id}/ci-status", response_model=ApplicationResponse)
async def update_app_ci_status(
    app_id: int,
    payload: CiStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_verify_ci_callback_token),
):
    """CI runner callback: update pipeline status on an application."""
    return await AppService(db).update_ci_status(app_id, payload)


@router.delete("/{app_id}")
async def delete_app(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tier(CnpTier.MAINTAINER)),
):
    app = await AppService(db).get_app(app_id)
    app_name = app.name
    await AppService(db).delete_app(app_id)
    audit = AuditService(db)
    await audit.log_action(current_user.id, "app.deleted", extra={"name": app_name})
    await emit_event(db, EventType.APP_DELETED, "warning", "app_service",
                     payload={"name": app_name},
                     actor_user_id=current_user.id)
    await db.commit()
    return {"msg": "Application deleted"}


class ExposeToggleRequest(BaseModel):
    expose: bool


@router.patch("/{app_id}/expose", response_model=ApplicationResponse)
async def toggle_expose(
    app_id: int,
    payload: ExposeToggleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tier(CnpTier.MAINTAINER)),
):
    """Enable or disable public internet exposure (nginx ingress) for all environments."""
    app = await AppService(db).update_expose(app_id, payload.expose)
    audit = AuditService(db)
    await audit.log_action(current_user.id, "app.expose.changed", app_id=app.id,
                           extra={"name": app.name, "expose": payload.expose})
    await emit_event(db, EventType.APP_EXPOSE_CHANGED, "info", "app_service",
                     app_id=app.id, payload={"name": app.name, "expose": payload.expose},
                     actor_user_id=current_user.id)
    await db.commit()
    return app


class AppScaleRequest(BaseModel):
    env: str  # "dev" | "prod" | "both"


def _resolve_scale_envs(env: str) -> List[str]:
    if env == "both":
        return ["dev", "prod"]
    if env in ("dev", "prod"):
        return [env]
    raise HTTPException(status_code=422, detail="env must be 'dev', 'prod', or 'both'")


async def _require_prod_tier(app_id: int, envs: List[str], current_user: User, db: AsyncSession) -> None:
    """Stopping/resuming production requires Owner tier on the app (or platform admin)."""
    if "prod" not in envs or current_user.is_admin:
        return
    tier = await get_effective_tier(current_user.id, app_id, db)
    if tier != CnpTier.OWNER:
        raise HTTPException(status_code=403, detail="Stopping or resuming production requires Owner tier or admin")


@router.post("/{app_id}/stop", response_model=ApplicationResponse)
async def stop_app(
    app_id: int,
    payload: AppScaleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tier(CnpTier.MAINTAINER)),
):
    """Manually scale an app's environment(s) to zero via a gitops commit."""
    envs = _resolve_scale_envs(payload.env)
    await _require_prod_tier(app_id, envs, current_user, db)
    app = await ScaleService(db).manual_stop(app_id, envs, actor_user_id=current_user.id)
    audit = AuditService(db)
    await audit.log_action(current_user.id, "app.scale.stop", app_id=app.id, extra={"envs": envs})
    for env in envs:
        await emit_event(db, EventType.APP_SCALE_STOPPED, "warning" if env == "prod" else "info", "scale_service",
                         app_id=app.id, payload={"name": app.name, "env": env},
                         actor_user_id=current_user.id)
    await db.commit()
    await db.refresh(app)
    return app


@router.post("/{app_id}/resume", response_model=ApplicationResponse)
async def resume_app(
    app_id: int,
    payload: AppScaleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tier(CnpTier.MAINTAINER)),
):
    """Manually resume an app's environment(s) via a gitops commit (clears scheduled or manual stop)."""
    envs = _resolve_scale_envs(payload.env)
    await _require_prod_tier(app_id, envs, current_user, db)
    app = await ScaleService(db).manual_resume(app_id, envs, actor_user_id=current_user.id)
    audit = AuditService(db)
    await audit.log_action(current_user.id, "app.scale.resume", app_id=app.id, extra={"envs": envs})
    for env in envs:
        await emit_event(db, EventType.APP_SCALE_RESUMED, "info", "scale_service",
                         app_id=app.id, payload={"name": app.name, "env": env},
                         actor_user_id=current_user.id)
    await db.commit()
    await db.refresh(app)
    return app


@router.get("/{app_id}/scale", response_model=AppScaleStateResponse)
async def get_app_scale_state(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_tier(CnpTier.VIEWER)),
):
    """Current stop/resume state per environment (dev/prod)."""
    states = await ScaleService(db).get_scale_states(app_id)
    return AppScaleStateResponse(
        dev=AppScaleStateItem(
            is_stopped=states["dev"].is_stopped,
            stop_reason=states["dev"].stop_reason.value if states["dev"].stop_reason else None,
            stopped_at=states["dev"].stopped_at,
            resumed_at=states["dev"].resumed_at,
        ) if "dev" in states else None,
        prod=AppScaleStateItem(
            is_stopped=states["prod"].is_stopped,
            stop_reason=states["prod"].stop_reason.value if states["prod"].stop_reason else None,
            stopped_at=states["prod"].stopped_at,
            resumed_at=states["prod"].resumed_at,
        ) if "prod" in states else None,
    )
