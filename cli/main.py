import typer
from cli.commands import auth, resources, credentials

app = typer.Typer(
    name="cnp",
    help="Cloud Native Platform CLI",
    add_completion=False
)

app.add_typer(auth.app, name="auth")
app.add_typer(resources.app, name="resources")
app.add_typer(credentials.app, name="credentials")

if __name__ == "__main__":
    app()
