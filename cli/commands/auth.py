import typer
import getpass
import socket
from cli.core.client import APIClient, get_base_url
from cli.core.config import load_config, save_config, CONFIG_FILE
from cli.core.output import print_error, print_success, console
import requests

app = typer.Typer(help="Manage authentication.")

@app.command()
def login(
    api_url: str = typer.Option("http://localhost:8000/api/v1", help="Base URL for the CNP API"),
    email: str = typer.Option(None, prompt="Email"),
):
    """Authenticate and generate a persistent API Key."""
    password = getpass.getpass("Password: ")

    try:
        # First login with JWT
        session = requests.Session()
        res = session.post(f"{api_url}/auth/login", json={"email": email, "password": password})
        res.raise_for_status()
        token = res.json()["access_token"]

        # Then create API Key
        session.headers.update({"Authorization": f"Bearer {token}"})
        hostname = socket.gethostname()
        res = session.post(f"{api_url}/auth/apikeys?label=CLI-{hostname}")
        res.raise_for_status()
        key_data = res.json()

        # Save to config
        config = load_config()
        config["api_url"] = api_url
        config["api_key"] = key_data["api_key"]
        config["user_email"] = email
        save_config(config)

        print_success(f"Logged in successfully. Config saved to {CONFIG_FILE}")

    except requests.exceptions.HTTPError as e:
        try:
            print_error(e.response.json().get("detail", str(e)))
        except:
            print_error(str(e))
    except Exception as e:
        print_error(str(e))

@app.command()
def logout():
    """Remove local config (does not revoke key remotely for now)."""
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
        print_success("Logged out. Local config removed.")
    else:
        print_error("Not currently logged in.")

@app.command()
def status():
    """Check current authentication status."""
    config = load_config()
    if not config.get("api_key"):
        print_error("Not logged in.")
        raise typer.Exit(1)

    console.print(f"User: [blue]{config.get('user_email')}[/blue]")
    console.print(f"API URL: [green]{config.get('api_url')}[/green]")
    console.print(f"API Key: ***{config.get('api_key')[-4:]}")
