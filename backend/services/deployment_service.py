from shared.models import DeploymentEnv, DeploymentResponse


def history_entry_to_deployment(app, env: DeploymentEnv, entry: dict) -> DeploymentResponse:
    """Projette une entrée `status.history` d'une Application ArgoCD."""
    initiated = entry.get("initiatedBy") or {}
    revisions = entry.get("revisions") or ([entry["revision"]] if entry.get("revision") else [])
    return DeploymentResponse(
        id=f"{app.id}:{env.value}:{entry['id']}",
        app_id=app.id,
        app_slug=app.slug,
        app_name=app.name,
        env=env,
        history_id=entry["id"],
        revisions=revisions,
        deployed_at=entry["deployedAt"],
        deploy_started_at=entry.get("deployStartedAt"),
        initiated_by=initiated.get("username") or None,
        automated=bool(initiated.get("automated")),
    )
