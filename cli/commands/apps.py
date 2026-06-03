import typer
from typing import Optional
from cli.core.client import client
from cli.core.config import load_config
from cli.core.output import print_error, print_success, print_table, print_json

app = typer.Typer(help="Manage CNP applications.")


@app.command("import")
def import_app(
    repo_url: str = typer.Option(..., "--repo-url", "-r", help="GitLab repository URL"),
    name: str = typer.Option(..., "--name", "-n", help="Application name"),
    owner: Optional[str] = typer.Option(None, "--owner", "-o", help="Owner (defaults to logged-in user)"),
    framework: Optional[str] = typer.Option(None, "--framework", "-f", help="Framework: python, generic (auto-detected if omitted)"),
    cluster_id: Optional[int] = typer.Option(None, "--cluster-id", "-c", help="Target cluster ID (optional)"),
):
    """Import an existing GitLab repo as a CNP application."""
    resolved_owner = owner or load_config().get("user_email", "")
    if not resolved_owner:
        print_error("Could not determine owner. Pass --owner or log in first (cnp auth login).")
        raise typer.Exit(1)

    payload: dict = {"name": name, "owner": resolved_owner, "repo_url": repo_url}
    if framework:
        payload["framework"] = framework
    if cluster_id is not None:
        payload["target_cluster_id"] = cluster_id

    try:
        data = client.post("/apps/import", json=payload)
        print_success(f"App '{data['name']}' imported (id={data['id']})")
        print_table(
            "Import result",
            ["Field", "Value"],
            [
                ["id", data["id"]],
                ["name", data["name"]],
                ["owner", data["owner"]],
                ["repo_url", data.get("repo_url") or "—"],
                ["framework", data.get("framework") or "—"],
                ["target_cluster_id", data.get("target_cluster_id") or "—"],
                ["status", data["status"]],
                ["ci_injected", data.get("ci_injected")],
            ],
        )
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("list")
def list_apps(
    output: str = typer.Option("table", "--output", "-o", help="Output format: table or json"),
):
    """List all CNP applications."""
    try:
        data = client.get("/apps/")
        if output == "json":
            print_json(data)
        else:
            columns = ["ID", "Name", "Owner", "Status", "Origin", "CI"]
            rows = [
                [
                    a["id"],
                    a["name"],
                    a.get("owner") or "—",
                    a["status"],
                    a.get("origin") or "—",
                    a.get("ci_injected"),
                ]
                for a in data
            ]
            print_table("Applications", columns, rows)
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("get")
def get_app(id: int = typer.Argument(..., help="Application ID")):
    """Get details of a CNP application."""
    try:
        data = client.get(f"/apps/{id}")
        print_json(data)
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("delete")
def delete_app(
    id: int = typer.Argument(..., help="Application ID"),
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Skip confirmation prompt"),
):
    """Delete a CNP application."""
    if not confirm:
        typer.confirm(f"Delete application {id}?", abort=True)
    try:
        client.delete(f"/apps/{id}")
        print_success(f"Application {id} deleted.")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)
