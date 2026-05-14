import typer
from cli.core.client import client
from cli.core.output import print_error, print_success, console

GITLAB_PAT_URL = "https://gitlab.cri.epita.fr/-/user_settings/personal_access_tokens"

app = typer.Typer(help="Manage GitLab EPITA credentials.")


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
    """Show how to create a Personal Access Token on gitlab.cri.epita.fr."""
    console.print("\n[bold orange1]GitLab Personal Access Token — guide[/bold orange1]\n")
    console.print(f"[bold]1.[/bold] Ouvrir la page des tokens :")
    console.print(f"   [blue underline]{GITLAB_PAT_URL}[/blue underline]\n")
    console.print("[bold]2.[/bold] Créer un token")
    console.print("   Nom : [italic]cnp-platform[/italic] — expiration : laissez vide.\n")
    console.print("[bold]3.[/bold] Scopes requis")
    console.print("   [bold green]api[/bold green]   [bold green]write_repository[/bold green]\n")
    console.print("[bold]4.[/bold] Copier le token (commence par [italic]glpat-[/italic]) — affiché une seule fois.\n")
    console.print("[bold]5.[/bold] Enregistrer via la CLI :")
    console.print("   [bold]cnp gitlab set[/bold]\n")


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
