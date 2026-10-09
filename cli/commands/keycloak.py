import typer

from cli.core.client import client
from cli.core.output import console, print_error, print_json, print_success, print_table

app = typer.Typer(help="Manage the Keycloak app-auth service for an application (4K-15/ADR-0026).")

_VALID_ENVS = ("dev", "prod")


def _resolve_app_id(slug: str) -> int:
    """Same convention as `cnp env` — users pass the app slug, we resolve it
    client-side against GET /apps (matches the portal, where users think in slugs)."""
    apps = client.get("/apps/")
    for a in apps:
        if a.get("slug") == slug:
            return a["id"]
    print_error(f"No application found with slug '{slug}'")
    raise typer.Exit(1)


def _validate_env(env: str) -> None:
    if env not in _VALID_ENVS:
        print_error("--env must be 'dev' or 'prod'")
        raise typer.Exit(1)


_STATE_LABELS = {
    "active": "active",
    "missing": "realm deleted (recreate with `cnp keycloak reprovision`)",
    "foreign": "realm name taken by another realm — contact a platform admin",
    "unknown": "unknown (Keycloak unreachable or disabled)",
}


def _state_label(env_status: dict) -> str:
    if not env_status["enabled"]:
        return "not activated"
    return _STATE_LABELS.get(env_status.get("state", "unknown"), env_status.get("state", "unknown"))


@app.command("status")
def status(
    app_slug: str = typer.Option(..., "--app", "-a", help="Application slug"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table or json"),
):
    """Show Keycloak status (dev + prod) for an application."""
    try:
        app_id = _resolve_app_id(app_slug)
        data = client.get(f"/apps/{app_id}/auth")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)

    if output == "json":
        print_json(data)
        return

    instance = data.get("instance")
    if instance:
        label = "Legacy configuration" if instance.get("source") == "legacy" else instance.get("instance_key")
        console.print("Instance:", label, "—", instance.get("cluster_name") or "—", markup=False)
        console.print(instance["public_url"], markup=False)
        if not instance.get("enabled"):
            print_error("Keycloak instance is unavailable")

    rows = [
        [
            env,
            _state_label(data[env]),
            data[env]["issuer_url"] or "—",
        ]
        for env in ("dev", "prod")
    ]
    print_table(f"Keycloak — {app_slug}", ["Env", "Status", "Issuer URL"], rows)
    if data.get("auth_warnings"):
        console.print(f"[yellow]Warnings:[/yellow] {', '.join(data['auth_warnings'])}")


@app.command("enable")
def enable(
    app_slug: str = typer.Option(..., "--app", "-a", help="Application slug"),
):
    """Activate Keycloak on an app that wasn't scaffolded/onboarded with it
    (provisions both dev and prod realms)."""
    try:
        app_id = _resolve_app_id(app_slug)
        data = client.post(f"/apps/{app_id}/auth")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)
    if data.get("auth_provisioned") is False or any(
        not data[env]["enabled"] or data[env].get("state") != "active" for env in _VALID_ENVS
    ):
        print_error("Keycloak provisioning did not complete. Retry activation after resolving the reported issue.")
        raise typer.Exit(1)
    print_success(f"Keycloak activated on '{app_slug}'")
    print_table(
        f"Keycloak — {app_slug}",
        ["Env", "Realm", "Status"],
        [[env, data[env]["realm"], _state_label(data[env])] for env in ("dev", "prod")],
    )


@app.command("console")
def console_access(
    app_slug: str = typer.Option(..., "--app", "-a", help="Application slug"),
    env: str = typer.Option(..., "--env", "-e", help="Environment: dev or prod"),
):
    """Create/reactivate a temporary console admin account for you and print the
    URL + credentials. The password is shown only once — copy it now."""
    _validate_env(env)
    try:
        app_id = _resolve_app_id(app_slug)
        data = client.post(f"/apps/{app_id}/auth/{env}/console-access")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)

    print_success(f"Console access granted for {app_slug} ({env}) — copy this now, it won't be shown again:")
    print_table(
        "Keycloak console access",
        ["Field", "Value"],
        [
            ["console_url", data["console_url"]],
            ["username", data["username"]],
            ["temporary_password", data["temporary_password"]],
        ],
    )


@app.command("reprovision")
def reprovision(
    app_slug: str = typer.Option(..., "--app", "-a", help="Application slug"),
    env: str = typer.Option(..., "--env", "-e", help="Environment: dev or prod"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt (for scripting)"),
):
    """Recreate a deleted realm from scratch. DESTRUCTIVE if a realm still exists:
    fails with a 409 rather than overwriting it — delete it first if that's really
    what you want. dev: Maintainer+. prod: Owner only."""
    _validate_env(env)
    if not yes:
        confirmed = typer.confirm(
            f"Recreate the {env} Keycloak realm for '{app_slug}'? "
            "This creates a brand new, EMPTY realm — existing users, roles and the "
            "client secret are permanently lost if the realm currently exists. "
            "Continue?"
        )
        if not confirmed:
            raise typer.Exit(0)

    try:
        app_id = _resolve_app_id(app_slug)
        data = client.post(f"/apps/{app_id}/auth/{env}/reprovision")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)
    print_success(f"Realm recreated for {app_slug} ({env}): {data[env]['realm']}")
