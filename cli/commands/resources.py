import typer
from typing import Optional
from cli.core.client import client
from cli.core.output import print_error, print_success, print_table, print_json

app = typer.Typer(help="Manage cloud resources.")

@app.command("list")
def list_resources(
    cloud: Optional[str] = typer.Option(None, help="Filter by cloud (aws, gcp, openstack)"),
    type: Optional[str] = typer.Option(None, help="Filter by type (vm, storage, network)"),
    output: str = typer.Option("table", help="Output format: table or json")
):
    """List resources."""
    try:
        params = {}
        if cloud: params["cloud"] = cloud
        if type: params["type"] = type

        data = client.get("/resources/", params=params)

        if output == "json":
            print_json(data)
        else:
            columns = ["ID", "Name", "Cloud", "Type", "Status", "External ID"]
            rows = [[r["id"], r["name"], r["cloud"].upper(), r["type"].upper(), r["status"], r["external_id"]] for r in data]
            print_table("Resources", columns, rows)

    except Exception as e:
        print_error(str(e))

@app.command("get")
def get_resource(id: int):
    """Get details of a specific resource."""
    try:
        data = client.get(f"/resources/{id}")
        print_json(data)
    except Exception as e:
        print_error(str(e))

@app.command("create")
def create_resource(
    cloud: str = typer.Option(..., help="Cloud provider (aws, gcp, openstack)"),
    type: str = typer.Option(..., help="Resource type (vm, storage, network)"),
    name: str = typer.Option(..., help="Name of the resource"),
    size: Optional[str] = typer.Option(None, help="Size/Type (e.g. t2.micro, 10GB)")
):
    """Create a new resource."""
    try:
        payload = {"cloud": cloud, "type": type, "name": name}
        if size:
            payload["size"] = size

        data = client.post("/resources/", json=payload)
        print_success(f"Resource created: {data['id']} - {data['external_id']}")
        print_json(data)
    except Exception as e:
        print_error(str(e))

@app.command("delete")
def delete_resource(
    id: int,
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Confirm deletion without prompt")
):
    """Delete a resource."""
    if not confirm:
        typer.confirm(f"Are you sure you want to delete resource {id}?", abort=True)

    try:
        client.delete(f"/resources/{id}")
        print_success(f"Resource {id} deletion initiated.")
    except Exception as e:
        print_error(str(e))
