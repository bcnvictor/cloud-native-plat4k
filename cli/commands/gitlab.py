import typer
from cli.core.client import client
from cli.core.output import print_error, print_success, print_table, console

GITLAB_PAT_URL = "https://gitlab.com/-/user_settings/personal_access_tokens"

app = typer.Typer(help="Manage GitLab credentials and team groups.")
groups_app = typer.Typer(help="Manage tracked GitLab team groups (admin only).")
app.add_typer(groups_app, name="groups")


@app.command("set")
def set_credentials(
    namespace: str = typer.Option(..., prompt=True, help="GitLab group or username"),
):
    """Save your GitLab Personal Access Token and namespace."""
    token = typer.prompt("GitLab PAT (glpat-...)", hide_input=True)
    if not token.strip():
        print_error("Token cannot be empty.")
        raise typer.Exit(1)

    try:
        client.post("/gitlab/credentials", json={"token": token.strip(), "namespace": namespace.strip()})
        print_success(f"GitLab credentials saved (namespace: {namespace.strip()}).")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)

    # Auto healthcheck
    typer.echo("Checking connection...")
    _run_healthcheck()


@app.command("status")
def status():
    """Check the GitLab connection using your stored token."""
    _run_healthcheck()


@app.command("remove")
def remove_credentials(
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Skip confirmation prompt"),
):
    """Delete your stored GitLab credentials."""
    if not confirm:
        typer.confirm("Remove your GitLab credentials?", abort=True)
    try:
        client.delete("/gitlab/credentials")
        print_success("GitLab credentials removed.")
    except Exception as e:
        print_error(str(e))


@app.command("guide")
def guide():
    """Show how to create a Personal Access Token on gitlab.com."""
    console.print("\n[bold orange1]GitLab Personal Access Token — guide[/bold orange1]\n")
    console.print("[bold]1.[/bold] Ouvrir la page des tokens :")
    console.print(f"   [blue underline]{GITLAB_PAT_URL}[/blue underline]\n")
    console.print("[bold]2.[/bold] Créer un token")
    console.print("   Nom : [italic]cnp-platform[/italic] — expiration : laissez vide.\n")
    console.print("[bold]3.[/bold] Scopes requis")
    console.print("   [bold green]api[/bold green]   [bold green]write_repository[/bold green]\n")
    console.print("[bold]4.[/bold] Copier le token (commence par [italic]glpat-[/italic]) — affiché une seule fois.\n")
    console.print("[bold]5.[/bold] Enregistrer via la CLI :")
    console.print("   [bold]cnp gitlab set[/bold]\n")


@app.command("sync")
def sync_gitlab(
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Skip confirmation prompt"),
):
    """Trigger a full GitLab membership reconciliation cycle (admin only)."""
    if not confirm:
        typer.confirm("Run a full GitLab sync now?", abort=True)
    try:
        data = client.post("/admin/sync-gitlab")
        if data.get("skipped"):
            console.print("[yellow]⚠[/yellow]  Sync skipped — GITLAB_BOT_TOKEN not configured.")
            return
        g = data.get("groups", {})
        p = data.get("projects", {})
        console.print("[green]✓[/green]  Sync complete")
        print_table(
            "Results",
            ["Scope", "Created", "Updated", "Revoked"],
            [
                ["groups", g.get("created", 0), g.get("updated", 0), g.get("revoked", 0)],
                ["projects", p.get("created", 0), p.get("updated", 0), p.get("revoked", 0)],
            ],
        )
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


# ── Groups subcommands ─────────────────────────────────────────────────────────

@groups_app.command("list")
def groups_list():
    """List GitLab groups tracked by CNP (admin only)."""
    try:
        data = client.get("/admin/gitlab-groups")
        if not data:
            typer.echo("No groups tracked yet. Use 'cnp gitlab groups add' to add one.")
            return
        print_table(
            "Tracked GitLab groups",
            ["ID", "Name", "Full Path", "Synced At"],
            [
                [
                    g["gitlab_group_id"],
                    g["name"],
                    g["full_path"],
                    g.get("synced_at") or "—",
                ]
                for g in data
            ],
        )
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@groups_app.command("add")
def groups_add(
    full_path: str = typer.Option(None, "--full-path", "-p", help="GitLab group full_path (e.g. my-org/my-team)"),
    gitlab_group_id: int = typer.Option(None, "--group-id", "-g", help="GitLab group numeric ID"),
):
    """Register a GitLab group to track in CNP (admin only)."""
    if not full_path and not gitlab_group_id:
        print_error("Provide either --full-path or --group-id.")
        raise typer.Exit(1)
    payload = {}
    if full_path:
        payload["full_path"] = full_path
    if gitlab_group_id:
        payload["gitlab_group_id"] = gitlab_group_id
    try:
        data = client.post("/admin/gitlab-groups", json=payload)
        print_success(f"Group '{data['name']}' ({data['full_path']}) registered (id={data['gitlab_group_id']})")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@groups_app.command("remove")
def groups_remove(
    gitlab_group_id: int = typer.Argument(..., help="GitLab group numeric ID"),
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Skip confirmation prompt"),
):
    """Remove a GitLab group from CNP tracking (admin only)."""
    if not confirm:
        typer.confirm(f"Remove group {gitlab_group_id} from tracking?", abort=True)
    try:
        client.delete(f"/admin/gitlab-groups/{gitlab_group_id}")
        print_success(f"Group {gitlab_group_id} removed.")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


# ── Internal ──────────────────────────────────────────────────────────────────

def _run_healthcheck():
    try:
        data = client.get("/gitlab/healthcheck")
    except Exception as e:
        print_error(str(e))
        return

    status = data.get("status")
    if status == "ok":
        user = data.get("authenticated_as", "?")
        console.print(f"[green]✓[/green] Connected — authenticated as [bold]{user}[/bold]")
    elif status == "not_configured":
        console.print("[yellow]⚠[/yellow]  No token configured. Run [bold]cnp gitlab set[/bold] or [bold]cnp gitlab guide[/bold].")
    else:
        detail = data.get("detail", "Connection failed.")
        console.print(f"[red]✗[/red]  {detail}")
