import typer
import json
from cli.core.client import client
from cli.core.output import print_error, print_success, print_table, print_json

app = typer.Typer(help="Manage cloud credentials.")

@app.command("list")
def list_credentials(output: str = typer.Option("table", help="Output format: table or json")):
    """List configured cloud credentials."""
    try:
        data = client.get("/credentials/")
        if output == "json":
            print_json(data)
        else:
            columns = ["ID", "Cloud", "Created At"]
            rows = [[r["id"], r["cloud"].upper(), r["created_at"]] for r in data]
            print_table("Cloud Credentials", columns, rows)
    except Exception as e:
        print_error(str(e))

@app.command("add")
def add_credential(
    cloud: str = typer.Option(..., help="Cloud provider (aws, gcp, openstack)")
):
    """Add new cloud credentials."""
    try:
        typer.echo(f"Enter credentials for {cloud} as JSON (e.g. {{\"aws_access_key_id\": \"...\"}}):")
        creds_str = typer.prompt("JSON payload")

        try:
            creds = json.loads(creds_str)
        except json.JSONDecodeError:
            print_error("Invalid JSON format.")
            raise typer.Exit(1)

        data = client.post("/credentials/", json={"cloud": cloud, "credentials": creds})
        print_success(f"Credentials for {cloud} added successfully (ID: {data['id']}).")

    except Exception as e:
        print_error(str(e))

@app.command("delete")
def delete_credential(
    id: int,
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Confirm deletion without prompt")
):
    """Delete cloud credentials."""
    if not confirm:
        typer.confirm(f"Are you sure you want to delete credential {id}?", abort=True)

    try:
        client.delete(f"/credentials/{id}")
        print_success(f"Credential {id} deleted.")
    except Exception as e:
        print_error(str(e))
