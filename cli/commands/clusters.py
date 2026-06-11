import typer
from cli.core.client import client
from cli.core.output import print_error, print_success, print_table, print_json

app = typer.Typer(help="Manage CNP cluster connections.")

_STATUS_LABEL = {
    "online":  "[green]● online[/green]",
    "offline": "[red]○ offline[/red]",
    "unknown": "[yellow]◌ unknown[/yellow]",
}


@app.command("list")
def list_clusters(
    output: str = typer.Option("table", "--output", "-o", help="Output format: table or json"),
):
    """List all registered clusters and their health status."""
    try:
        data = client.get("/clusters/")
        if output == "json":
            print_json(data)
        else:
            columns = ["ID", "Name", "Status", "Endpoint", "Last seen"]
            rows = [
                [
                    c["id"],
                    c["name"],
                    _STATUS_LABEL.get(c.get("status", "unknown"), c.get("status", "—")),
                    c.get("endpoint") or "—",
                    c.get("last_seen_at") or "—",
                ]
                for c in data
            ]
            print_table("Clusters", columns, rows)
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("get")
def get_cluster(id: int = typer.Argument(..., help="Cluster ID")):
    """Get details of a cluster connection."""
    try:
        data = client.get(f"/clusters/{id}")
        print_json(data)
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("delete")
def delete_cluster(
    id: int = typer.Argument(..., help="Cluster ID"),
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Skip confirmation prompt"),
):
    """Delete a cluster connection (admin only)."""
    if not confirm:
        typer.confirm(f"Delete cluster {id}?", abort=True)
    try:
        client.delete(f"/clusters/{id}")
        print_success(f"Cluster {id} deleted.")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)
