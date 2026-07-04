from typing import List

import typer

from cli.core.client import client
from cli.core.output import print_error, print_success, print_table

app = typer.Typer(help="Manage application environment variables.")

_VALID_ENVS = ("dev", "prod")


def _resolve_app_id(slug: str) -> int:
    """CLI convention elsewhere is numeric IDs (cnp app get <id>); env vars use
    --app <slug> instead (matches the portal, where users think in slugs), so we
    resolve it client-side against GET /apps — no backend slug filter needed."""
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


@app.command("list")
def list_env(
    app_slug: str = typer.Option(..., "--app", "-a", help="Application slug"),
    env: str = typer.Option(..., "--env", "-e", help="Environment: dev or prod"),
):
    """List environment variable keys and their set/unset status."""
    _validate_env(env)
    try:
        app_id = _resolve_app_id(app_slug)
        data = client.get(f"/apps/{app_id}/env/{env}")
        rows = [[k["key"], "set" if k["is_set"] else "unset"] for k in data["keys"]]
        print_table(f"Env vars — {app_slug} ({env})", ["Key", "Status"], rows)
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("set")
def set_env(
    pairs: List[str] = typer.Argument(..., help="One or more KEY=VALUE pairs"),
    app_slug: str = typer.Option(..., "--app", "-a", help="Application slug"),
    env: str = typer.Option(..., "--env", "-e", help="Environment: dev or prod"),
):
    """Set one or more environment variables (creates or updates, single API call)."""
    _validate_env(env)
    variables = {}
    for pair in pairs:
        if "=" not in pair:
            print_error(f"Invalid KEY=VALUE pair: '{pair}'")
            raise typer.Exit(1)
        key, value = pair.split("=", 1)
        variables[key] = value

    try:
        app_id = _resolve_app_id(app_slug)
        client.put(f"/apps/{app_id}/env/{env}", json={"variables": variables})
        print_success(f"Set {len(variables)} variable(s) on {app_slug} ({env})")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("unset")
def unset_env(
    keys: List[str] = typer.Argument(..., help="One or more keys to remove"),
    app_slug: str = typer.Option(..., "--app", "-a", help="Application slug"),
    env: str = typer.Option(..., "--env", "-e", help="Environment: dev or prod"),
):
    """Remove one or more environment variables."""
    _validate_env(env)
    try:
        app_id = _resolve_app_id(app_slug)
        for key in keys:
            client.delete(f"/apps/{app_id}/env/{env}/{key}")
        print_success(f"Removed {len(keys)} variable(s) from {app_slug} ({env})")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("pull")
def pull_env(
    app_slug: str = typer.Option(..., "--app", "-a", help="Application slug"),
    env: str = typer.Option("dev", "--env", "-e", help="Environment — dev only"),
    output: str = typer.Option(".env.local", "--output", "-o", help="Output file path"),
):
    """Write real values to a local .env file. Dev only — prod values are never
    exposed through the API, by design (see ADR-0025 addendum)."""
    if env != "dev":
        print_error("cnp env pull is only available for --env dev — prod values are never exposed via the API.")
        raise typer.Exit(1)
    try:
        app_id = _resolve_app_id(app_slug)
        values = client.get(f"/apps/{app_id}/env/dev/values")
        with open(output, "w") as f:
            for key, value in values.items():
                f.write(f"{key}={value}\n")
        print_success(f"Wrote {len(values)} variable(s) to {output}")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)
