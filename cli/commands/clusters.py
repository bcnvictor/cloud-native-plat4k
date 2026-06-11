import typer
import os
from cli.core.client import client
from cli.core.output import print_error, print_success, print_table, print_json

app = typer.Typer(help="Manage Kubernetes cluster connections.")

@app.command("list")
def list_clusters(output: str = typer.Option("table", help="Output format: table or json")):
    """List all registered Kubernetes clusters."""
    try:
        data = client.get("/clusters/")
        if output == "json":
            print_json(data)
        else:
            columns = ["ID", "Name", "Endpoint", "Vault Secret Ref", "Created At"]
            rows = [
                [
                    r["id"],
                    r["name"],
                    r["endpoint"],
                    r["kubeconfig_secret_ref"],
                    r["created_at"]
                ]
                for r in data
            ]
            print_table("Kubernetes Clusters", columns, rows)
    except Exception as e:
        print_error(str(e))

@app.command("add")
def add_cluster(
    name: str = typer.Option(..., help="Unique name for the cluster"),
    endpoint: str = typer.Option(..., help="Kubernetes API server endpoint URL (e.g. https://1.2.3.4:6443)"),
    kubeconfig: str = typer.Option(..., help="Path to the kubeconfig YAML file")
):
    """Register a new Kubernetes cluster connection."""
    try:
        if not os.path.exists(kubeconfig):
            print_error(f"Kubeconfig file not found at path: {kubeconfig}")
            raise typer.Exit(1)

        try:
            with open(kubeconfig, "r") as f:
                kubeconfig_content = f.read()
        except Exception as e:
            print_error(f"Failed to read kubeconfig file: {e}")
            raise typer.Exit(1)

        payload = {
            "name": name,
            "endpoint": endpoint,
            "kubeconfig": kubeconfig_content
        }

        data = client.post("/clusters/", json=payload)
        print_success(f"Cluster '{name}' successfully registered (ID: {data['id']}).")
    except Exception as e:
        print_error(str(e))

@app.command("update")
def update_cluster(
    id: int = typer.Argument(..., help="ID of the cluster to update"),
    name: str = typer.Option(None, help="New name for the cluster"),
    endpoint: str = typer.Option(None, help="New Kubernetes API server endpoint URL"),
    kubeconfig: str = typer.Option(None, help="Path to a new kubeconfig YAML file to update in Vault")
):
    """Update an existing Kubernetes cluster connection's details or kubeconfig."""
    try:
        payload = {}
        if name is not None:
            payload["name"] = name
        if endpoint is not None:
            payload["endpoint"] = endpoint
        if kubeconfig is not None:
            if not os.path.exists(kubeconfig):
                print_error(f"Kubeconfig file not found at path: {kubeconfig}")
                raise typer.Exit(1)
            try:
                with open(kubeconfig, "r") as f:
                    payload["kubeconfig"] = f.read()
            except Exception as e:
                print_error(f"Failed to read kubeconfig file: {e}")
                raise typer.Exit(1)

        if not payload:
            print_error("No fields to update. Please specify --name, --endpoint, or --kubeconfig.")
            raise typer.Exit(1)

        data = client.put(f"/clusters/{id}", json=payload)
        print_success(f"Cluster connection {id} updated successfully.")
    except Exception as e:
        print_error(str(e))

@app.command("delete")
def delete_cluster(
    id: int = typer.Argument(..., help="ID of the cluster connection to delete"),
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Confirm deletion without prompting")
):
    """Delete a registered Kubernetes cluster connection."""
    if not confirm:
        typer.confirm(f"Are you sure you want to delete cluster connection {id}?", abort=True)

    try:
        client.delete(f"/clusters/{id}")
        print_success(f"Cluster connection {id} deleted successfully.")
    except Exception as e:
        print_error(str(e))
