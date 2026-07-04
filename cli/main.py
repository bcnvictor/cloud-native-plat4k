import typer
from cli.commands import auth, resources, credentials, gitlab, apps, clusters, env
from cli.core.config import DOCS_URL

app = typer.Typer(
    name="cnp",
    help="Cloud Native Platform CLI",
    add_completion=False
)


@app.command()
def docs():
    """Ouvre la documentation CNP dans le navigateur."""
    import webbrowser
    typer.echo(f"Ouverture de la documentation : {DOCS_URL}")
    webbrowser.open(DOCS_URL)

app.add_typer(auth.app, name="auth")
app.add_typer(apps.app, name="app")
app.add_typer(env.app, name="env")
app.add_typer(clusters.app, name="cluster")
app.add_typer(resources.app, name="resources")
app.add_typer(credentials.app, name="credentials")
app.add_typer(gitlab.app, name="gitlab")
app.add_typer(clusters.app, name="clusters")

if __name__ == "__main__":
    app()
