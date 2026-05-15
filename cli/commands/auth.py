import typer
import getpass
import socket
from cli.core.client import APIClient, get_base_url
from cli.core.config import load_config, save_config, CONFIG_FILE
from cli.core.output import print_error, print_success, console
import requests
import webbrowser
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

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


@app.command("oauth-login")
def oauth_login(
    api_url: str = typer.Option("http://localhost:8000/api/v1", help="Base URL for the CNP API"),
    callback_port: int = typer.Option(8765, help="Local port for OAuth callback"),
):
    """Open browser to start GitLab OAuth flow, then auto-capture token via local callback."""
    try:
        token_box = {"token": None, "email": None}
        event = threading.Event()

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)
                token = params.get("access_token", [None])[0]
                email = params.get("email", [None])[0]
                if token:
                    token_box["token"] = token
                    token_box["email"] = email
                    event.set()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"<html><body><h2>Login OK</h2><p>You can close this window.</p></body></html>")
                else:
                    self.send_response(400)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"Missing access_token")

            def log_message(self, format, *args):
                return

        server = HTTPServer(("localhost", callback_port), CallbackHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        return_to = f"http://localhost:{callback_port}/callback"
        auth_url = f"{api_url}/auth/gitlab/authorize?return_to={return_to}"
        console.print(f"Opening browser to: [green]{auth_url}[/green]")
        webbrowser.open(auth_url)

        if not event.wait(timeout=180):
            server.shutdown()
            print_error("Timeout waiting for OAuth callback")
            raise typer.Exit(code=1)

        server.shutdown()
        token = token_box["token"]
        if not token:
            print_error("No access token received")
            raise typer.Exit(code=1)

        session = requests.Session()
        session.headers.update({"Authorization": f"Bearer {token}"})
        hostname = socket.gethostname()
        res = session.post(f"{api_url}/auth/apikeys?label=CLI-{hostname}")
        res.raise_for_status()
        key_data = res.json()

        config = load_config()
        config["api_url"] = api_url
        config["api_key"] = key_data["api_key"]
        if token_box.get("email"):
            config["user_email"] = token_box["email"]
        save_config(config)

        print_success(f"Logged in via OAuth. API key saved to {CONFIG_FILE}")

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
