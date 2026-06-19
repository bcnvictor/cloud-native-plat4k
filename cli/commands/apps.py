import typer
from typing import Optional
from cli.core.client import client
from cli.core.config import load_config
from cli.core.output import print_error, print_success, print_table, print_json, console

app = typer.Typer(help="Manage CNP applications.")


@app.command("scaffold")
def scaffold_app(
    name: str = typer.Option(..., "--name", "-n", help="Application name"),
    template: str = typer.Option(..., "--template", "-t", help="Template name in GITLAB_TEMPLATES_NAMESPACE"),
    owner: Optional[str] = typer.Option(None, "--owner", "-o", help="Owner (defaults to logged-in user)"),
    port: int = typer.Option(8000, "--port", "-p", help="Container port"),
    replicas: int = typer.Option(1, "--replicas", "-r", help="Initial number of pods"),
    postgresql: bool = typer.Option(False, "--postgresql", help="Provision a PostgreSQL backing service"),
):
    """Scaffold a new application from a CNP template."""
    resolved_owner = owner or load_config().get("user_email", "")
    if not resolved_owner:
        print_error("Could not determine owner. Pass --owner or log in first (cnp auth login).")
        raise typer.Exit(1)

    services = ["postgresql"] if postgresql else []
    payload = {
        "name": name,
        "owner": resolved_owner,
        "template": template,
        "scaffolding": {"port": port, "replicas": replicas, "services": services},
    }

    try:
        data = client.post("/apps/scaffold", json=payload)
        print_success(f"App '{data['name']}' scaffolded (id={data['id']})")
        print_table(
            "Scaffold result",
            ["Field", "Value"],
            [
                ["id", data["id"]],
                ["name", data["name"]],
                ["owner", data["owner"]],
                ["repo_url", data.get("repo_url") or "—"],
                ["framework", data.get("framework") or "—"],
                ["status", data["status"]],
                ["ci_injected", data.get("ci_injected")],
            ],
        )
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("onboard")
def onboard_app(
    repo_url: str = typer.Option(..., "--repo-url", "-r", help="Internal GitLab repository URL"),
    name: str = typer.Option(..., "--name", "-n", help="Application name"),
    owner: Optional[str] = typer.Option(None, "--owner", "-o", help="Owner (defaults to logged-in user)"),
    framework: Optional[str] = typer.Option(None, "--framework", "-f", help="Framework: python, generic (auto-detected if omitted)"),
    cluster_id: Optional[int] = typer.Option(None, "--cluster-id", "-c", help="Target cluster ID (optional)"),
):
    """Onboard an existing internal GitLab repo as a CNP application."""
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
        data = client.post("/apps/onboard", json=payload)
        print_success(f"App '{data['name']}' onboarded (id={data['id']})")
        print_table(
            "Onboard result",
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


@app.command("import")
def import_app(
    source_url: str = typer.Option(..., "--source-url", "-s", help="Public GitHub or GitLab URL to import"),
    name: str = typer.Option(..., "--name", "-n", help="Application name"),
    owner: Optional[str] = typer.Option(None, "--owner", "-o", help="Owner (defaults to logged-in user)"),
    framework: Optional[str] = typer.Option(None, "--framework", "-f", help="Framework: python, generic (auto-detected if omitted)"),
    cluster_id: Optional[int] = typer.Option(None, "--cluster-id", "-c", help="Target cluster ID (optional)"),
    raw: bool = typer.Option(False, "--raw", help="Import as-is, skip CI injection"),
):
    """Import a public external repo (GitHub/GitLab) into cnp-apps."""
    resolved_owner = owner or load_config().get("user_email", "")
    if not resolved_owner:
        print_error("Could not determine owner. Pass --owner or log in first (cnp auth login).")
        raise typer.Exit(1)

    payload: dict = {"name": name, "owner": resolved_owner, "source_url": source_url, "raw": raw}
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
                ["source_url", data.get("source_url") or "—"],
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


@app.command("credentials")
def get_credentials(
    id: int = typer.Argument(..., help="Application ID"),
    namespace: str = typer.Option(..., "--namespace", "-n", help="Kubernetes namespace where the app is deployed"),
):
    """Get PostgreSQL credentials for a CNP application."""
    try:
        data = client.get(f"/apps/{id}/services/postgresql/credentials", params={"namespace": namespace})
        print_table(
            "PostgreSQL credentials",
            ["Field", "Value"],
            [
                ["host", data["host"]],
                ["port", data["port"]],
                ["username", data["username"]],
                ["password", data["password"]],
                ["database", data["database"]],
                ["DATABASE_URL", data["database_url"]],
            ],
        )
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


@app.command("members")
def list_members(
    id: int = typer.Argument(..., help="Application ID"),
):
    """List members of a CNP application (requires Maintainer+)."""
    try:
        data = client.get(f"/apps/{id}/members")
        if not data:
            typer.echo("No members found.")
            return
        print_table(
            f"Members — app {id}",
            ["CNP User ID", "Display Name", "Access Level", "Tier", "Status"],
            [
                [
                    m.get("cnp_user_id") or "—",
                    m.get("display_name") or "—",
                    m.get("access_level"),
                    m.get("tier_cnp"),
                    m.get("status"),
                ]
                for m in data
            ],
        )
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("add-member")
def add_member(
    id: int = typer.Argument(..., help="Application ID"),
    gitlab_user_id: int = typer.Option(..., "--gitlab-user-id", "-u", help="GitLab numeric user ID"),
    access_level: int = typer.Option(30, "--access-level", "-a", help="Access level (10=Guest, 30=Developer, 40=Maintainer, 50=Owner)"),
):
    """Add a GitLab user to an app project (write-through, requires Maintainer+)."""
    try:
        data = client.post(f"/apps/{id}/members", json={"gitlab_user_id": gitlab_user_id, "access_level": access_level})
        print_success(f"Member added — tier: {data.get('tier_cnp')}, status: {data.get('status')}")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("invite")
def invite_member(
    id: int = typer.Argument(..., help="Application ID"),
    email: str = typer.Option(..., "--email", "-e", help="Email address to invite"),
    access_level: int = typer.Option(30, "--access-level", "-a", help="Access level (10=Guest, 30=Developer, 40=Maintainer, 50=Owner)"),
):
    """Invite a user by email to an app project (write-through, requires Maintainer+)."""
    try:
        data = client.post(f"/apps/{id}/invitations", json={"email": email, "access_level": access_level})
        print_success(f"Invitation sent to {email} — tier: {data.get('tier_cnp')}, status: {data.get('status')}")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("access")
def my_access(
    id: int = typer.Argument(..., help="Application ID"),
):
    """Show your effective access tier on a CNP application."""
    try:
        data = client.get(f"/apps/{id}/my-access")
        tier = data.get("tier", "—")
        is_admin = data.get("is_admin", False)
        console.print(f"Tier: [bold]{tier}[/bold]" + ("  [yellow](admin override)[/yellow]" if is_admin else ""))
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)
