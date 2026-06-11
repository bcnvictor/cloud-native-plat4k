import typer
from cli.commands import auth, resources, credentials, gitlab, apps, clusters

app = typer.Typer(
    name="cnp",
    help="Cloud Native Platform CLI",
    add_completion=False
)

app.add_typer(auth.app, name="auth")
app.add_typer(apps.app, name="app")
app.add_typer(resources.app, name="resources")
app.add_typer(credentials.app, name="credentials")
app.add_typer(gitlab.app, name="gitlab")
app.add_typer(clusters.app, name="clusters")

if __name__ == "__main__":
    app()
