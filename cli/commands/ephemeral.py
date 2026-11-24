"""Environnements éphémères (ADR-0030, 4K-289).

`cnp env` gère déjà les variables d'environnement (ADR-0025) : les envs éphémères ont
leur propre groupe, `cnp ephemeral`.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import typer

from cli.core.client import client
from cli.core.output import console, print_error, print_json, print_success, print_table

app = typer.Typer(help="Manage ephemeral environments created from a branch (ADR-0030).")


def _resolve_app_id(slug: str) -> int:
    """Same convention as `cnp env` and `cnp keycloak`: users pass the app slug."""
    for a in client.get("/apps/"):
        if a.get("slug") == slug:
            return a["id"]
    print_error(f"No application found with slug '{slug}'")
    raise typer.Exit(1)


def _api(call: Callable[[], Any]) -> Any:
    """Run an API call; on failure print the API error and exit 1.

    cli.core.client raises a bare Exception carrying the API `detail`, hence the broad catch.
    """
    try:
        return call()
    except typer.Exit:
        raise
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1) from e


def ttl_remaining(expires_at: str, now: datetime | None = None) -> str:
    """Remaining time before expiry: '2d 3h', '5h 12m', '8m' or 'expired'."""
    now = now or datetime.now(UTC)
    expires = datetime.fromisoformat(expires_at)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    minutes = int((expires - now).total_seconds() // 60)
    if minutes < 0 or expires <= now:
        return "expired"
    days, rest = divmod(minutes, 1440)
    hours, mins = divmod(rest, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {mins}m"
    return f"{max(mins, 1)}m"


def _find_env(app_id: int, env: str) -> dict:
    """An environment by slug (feat-login), full name (shop--feat-login) or branch."""
    for e in client.get(f"/apps/{app_id}/ephemeral-envs"):
        if env in (e["slug"], e["name"], e["branch"]):
            return e
    print_error(f"No ephemeral environment '{env}' for this application (see `cnp ephemeral list`)")
    raise typer.Exit(1)


@app.command("list")
def list_envs(
    app_slug: str = typer.Option(..., "--app", "-a", help="Application slug"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table or json"),
):
    """List the ephemeral environments of an application."""
    app_id = _api(lambda: _resolve_app_id(app_slug))
    envs = _api(lambda: client.get(f"/apps/{app_id}/ephemeral-envs"))

    if output == "json":
        print_json(envs)
        return
    if not envs:
        console.print(f"No ephemeral environment for {app_slug}. Create one with `cnp ephemeral create`.")
        return
    rows = [
        [
            e["name"],
            e["branch"],
            e["status"],
            e["url"] if e["status"] == "active" and e.get("url") else "—",
            "—" if e["status"] == "destroying" else ttl_remaining(e["expires_at"]),
            e.get("image_tag") or "—",
        ]
        for e in envs
    ]
    print_table(f"Ephemeral environments — {app_slug}", ["Name", "Branch", "Status", "URL", "TTL left", "Image"], rows)


@app.command("branches")
def branches(app_slug: str = typer.Option(..., "--app", "-a", help="Application slug")):
    """List the branches an environment can be created from (default branch excluded)."""
    app_id = _api(lambda: _resolve_app_id(app_slug))
    names = _api(lambda: client.get(f"/apps/{app_id}/ephemeral-envs/branches"))
    for name in names:
        console.print(name, markup=False)


@app.command("create")
def create(
    app_slug: str = typer.Option(..., "--app", "-a", help="Application slug"),
    branch: str = typer.Option(..., "--branch", "-b", help="Git branch to deploy"),
    ttl: int = typer.Option(None, "--ttl", help="Time to live in hours (default: platform setting, 24h)"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table or json"),
):
    """Create an ephemeral environment from a branch."""
    payload: dict = {"branch": branch}
    if ttl is not None:
        payload["ttl_hours"] = ttl
    app_id = _api(lambda: _resolve_app_id(app_slug))
    env = _api(lambda: client.post(f"/apps/{app_id}/ephemeral-envs", json=payload))

    if output == "json":
        print_json(env)
        return
    if env["status"] == "failed":
        print_error(f"{env['name']} created but its pipeline could not be started: push to the branch to retry.")
        raise typer.Exit(1)
    print_success(f"{env['name']} requested: building branch {env['branch']}.")
    console.print(f"URL once active: {env['url']}", markup=False)
    console.print(f"Expires in {ttl_remaining(env['expires_at'])}. Follow it with `cnp ephemeral list --app {app_slug}`.")


@app.command("destroy")
def destroy(
    app_slug: str = typer.Option(..., "--app", "-a", help="Application slug"),
    env: str = typer.Argument(..., help="Environment slug, full name or branch"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Destroy one ephemeral environment (dev, prod and the repository are not affected)."""
    app_id = _api(lambda: _resolve_app_id(app_slug))
    target = _api(lambda: _find_env(app_id, env))

    if not confirm:
        typer.confirm(f"Destroy {target['name']} (branch {target['branch']}) and everything in its namespace?", abort=True)
    result = _api(lambda: client.delete(f"/apps/{app_id}/ephemeral-envs/{target['id']}"))

    if result["status"] == "destroyed":
        print_success(f"{result['name']} destroyed.")
    else:
        print_success(f"Destruction of {result['name']} started: it disappears once ArgoCD has removed its namespace.")
