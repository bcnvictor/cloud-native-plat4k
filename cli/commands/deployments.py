import typer
from cli.core.client import client
from cli.core.output import console, print_error, print_json, print_table

app = typer.Typer(help="Inspect application deployments (ArgoCD sync history).")

_ENVS = ("dev", "prod")


def _by(d: dict) -> str:
    return d.get("initiated_by") or "auto"


def _revision(d: dict) -> str:
    return (d.get("revisions") or [""])[0][:7]


@app.command("list")
def list_deployments(
    app_id: int = typer.Option(None, "--app", help="Filter by application ID"),
    env: str = typer.Option(None, "--env", help="Filter by environment: dev or prod"),
    limit: int = typer.Option(50, "--limit", help="Maximum number of deployments (1-200)"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table or json"),
):
    """List recent deployments, newest first."""
    if env is not None and env not in _ENVS:
        print_error("--env must be 'dev' or 'prod'")
        raise typer.Exit(1)
    params = {"limit": limit}
    if app_id is not None:
        params["app_id"] = app_id
    if env is not None:
        params["env"] = env
    try:
        data = client.get("/deployments/", params=params)
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)

    if output == "json":
        print_json(data)
        return
    columns = ["ID", "App", "Env", "Revision", "Deployed at", "By"]
    rows = [
        [d["id"], d["app_slug"], d["env"], _revision(d), d["deployed_at"], _by(d)]
        for d in data["items"]
    ]
    print_table("Deployments", columns, rows)
    for u in data["unavailable"]:
        console.print(f"[yellow]Warning:[/yellow] app {u['app_id']} ({u['env']}) unavailable: {u['reason']}")


@app.command("get")
def get_deployment(
    deployment_id: str = typer.Argument(..., help="Deployment ID, e.g. 42:prod:17"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table or json"),
):
    """Show one deployment."""
    try:
        d = client.get(f"/deployments/{deployment_id}")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)

    if output == "json":
        print_json(d)
        return
    rows = [
        ["ID", d["id"]],
        ["App", f"{d['app_name']} ({d['app_slug']}, #{d['app_id']})"],
        ["Env", d["env"]],
        ["History ID", d["history_id"]],
        ["Revisions", ", ".join(d["revisions"]) or "-"],
        ["Deploy started at", d.get("deploy_started_at") or "-"],
        ["Deployed at", d["deployed_at"]],
        ["By", _by(d)],
    ]
    print_table("Deployment", ["Field", "Value"], rows)
