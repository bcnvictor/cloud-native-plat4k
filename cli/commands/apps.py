import json
from datetime import datetime
from enum import Enum
from typing import Annotated, Optional

import typer
from rich.text import Text

from cli.core.client import client
from cli.core.config import load_config
from cli.core.output import console, print_error, print_json, print_success, print_table

app = typer.Typer(help="Manage CNP applications.")


@app.command("scaffold")
def scaffold_app(
    name: str = typer.Option(..., "--name", "-n", help="Application name"),
    template: str = typer.Option(..., "--template", "-t", help="Template name in GITLAB_TEMPLATES_NAMESPACE"),
    owner: Optional[str] = typer.Option(None, "--owner", "-o", help="Owner (defaults to logged-in user)"),
    port: int = typer.Option(8000, "--port", "-p", help="Container port"),
    replicas: int = typer.Option(1, "--replicas", "-r", help="Initial number of pods"),
    postgresql: bool = typer.Option(False, "--postgresql", help="Provision a PostgreSQL backing service"),
    keycloak: bool = typer.Option(
        False, "--keycloak", help="Provision Keycloak app-auth (realm per env, see 'cnp keycloak')"
    ),
):
    """Scaffold a new application from a CNP template."""
    resolved_owner = owner or load_config().get("user_email", "")
    if not resolved_owner:
        print_error("Could not determine owner. Pass --owner or log in first (cnp auth login).")
        raise typer.Exit(1)

    services = []
    if postgresql:
        services.append("postgresql")
    if keycloak:
        services.append("keycloak")
    payload = {
        "name": name,
        "owner": resolved_owner,
        "template": template,
        "scaffolding": {"port": port, "replicas": replicas, "services": services},
    }

    try:
        data = client.post("/apps/scaffold", json=payload)
        print_success(f"App '{data['name']}' scaffolded (id={data['id']})")
        print_table(
            "Scaffold result",
            ["Field", "Value"],
            [
                ["id", data["id"]],
                ["name", data["name"]],
                ["owner", data["owner"]],
                ["repo_url", data.get("repo_url") or "—"],
                ["framework", data.get("framework") or "—"],
                ["status", data["status"]],
                ["ci_injected", data.get("ci_injected")],
                ["auth_enabled", data.get("auth_enabled")],
                ["auth_provisioned", data.get("auth_provisioned")],
            ],
        )
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("onboard")
def onboard_app(
    repo_url: str = typer.Option(..., "--repo-url", "-r", help="Internal GitLab repository URL"),
    name: str = typer.Option(..., "--name", "-n", help="Application name"),
    owner: Optional[str] = typer.Option(None, "--owner", "-o", help="Owner (defaults to logged-in user)"),
    framework: Optional[str] = typer.Option(None, "--framework", "-f", help="Framework: python, generic (auto-detected if omitted)"),
    cluster_id: Optional[int] = typer.Option(None, "--cluster-id", "-c", help="Target cluster ID (optional)"),
    keycloak: bool = typer.Option(
        False, "--keycloak", help="Provision Keycloak app-auth (mode A: credentials only, no code injection)"
    ),
):
    """Onboard an existing internal GitLab repo as a CNP application."""
    resolved_owner = owner or load_config().get("user_email", "")
    if not resolved_owner:
        print_error("Could not determine owner. Pass --owner or log in first (cnp auth login).")
        raise typer.Exit(1)

    payload: dict = {"name": name, "owner": resolved_owner, "repo_url": repo_url}
    if framework:
        payload["framework"] = framework
    if cluster_id is not None:
        payload["target_cluster_id"] = cluster_id
    if keycloak:
        payload["services"] = ["keycloak"]

    try:
        data = client.post("/apps/onboard", json=payload)
        print_success(f"App '{data['name']}' onboarded (id={data['id']})")
        print_table(
            "Onboard result",
            ["Field", "Value"],
            [
                ["id", data["id"]],
                ["name", data["name"]],
                ["owner", data["owner"]],
                ["repo_url", data.get("repo_url") or "—"],
                ["framework", data.get("framework") or "—"],
                ["target_cluster_id", data.get("target_cluster_id") or "—"],
                ["status", data["status"]],
                ["ci_injected", data.get("ci_injected")],
                ["auth_enabled", data.get("auth_enabled")],
                ["auth_provisioned", data.get("auth_provisioned")],
                ["auth_warnings", ", ".join(data.get("auth_warnings") or []) or "—"],
            ],
        )
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("import")
def import_app(
    source_url: str = typer.Option(..., "--source-url", "-s", help="Public GitHub or GitLab URL to import"),
    name: str = typer.Option(..., "--name", "-n", help="Application name"),
    owner: Optional[str] = typer.Option(None, "--owner", "-o", help="Owner (defaults to logged-in user)"),
    framework: Optional[str] = typer.Option(None, "--framework", "-f", help="Framework: python, generic (auto-detected if omitted)"),
    cluster_id: Optional[int] = typer.Option(None, "--cluster-id", "-c", help="Target cluster ID (optional)"),
    raw: bool = typer.Option(False, "--raw", help="Import as-is, skip CI injection"),
):
    """Import a public external repo (GitHub/GitLab) into cnp-apps."""
    resolved_owner = owner or load_config().get("user_email", "")
    if not resolved_owner:
        print_error("Could not determine owner. Pass --owner or log in first (cnp auth login).")
        raise typer.Exit(1)

    payload: dict = {"name": name, "owner": resolved_owner, "source_url": source_url, "raw": raw}
    if framework:
        payload["framework"] = framework
    if cluster_id is not None:
        payload["target_cluster_id"] = cluster_id

    try:
        data = client.post("/apps/import", json=payload)
        print_success(f"App '{data['name']}' imported (id={data['id']})")
        print_table(
            "Import result",
            ["Field", "Value"],
            [
                ["id", data["id"]],
                ["name", data["name"]],
                ["owner", data["owner"]],
                ["repo_url", data.get("repo_url") or "—"],
                ["source_url", data.get("source_url") or "—"],
                ["framework", data.get("framework") or "—"],
                ["target_cluster_id", data.get("target_cluster_id") or "—"],
                ["status", data["status"]],
                ["ci_injected", data.get("ci_injected")],
            ],
        )
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("list")
def list_apps(
    output: str = typer.Option("table", "--output", "-o", help="Output format: table or json"),
):
    """List all CNP applications."""
    try:
        data = client.get("/apps/")
        if output == "json":
            print_json(data)
        else:
            columns = ["ID", "Name", "Owner", "Status", "Origin", "CI"]
            rows = [
                [
                    a["id"],
                    a["name"],
                    a.get("owner") or "—",
                    a["status"],
                    a.get("origin") or "—",
                    a.get("ci_injected"),
                ]
                for a in data
            ]
            print_table("Applications", columns, rows)
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("get")
def get_app(id: int = typer.Argument(..., help="Application ID")):
    """Get details of a CNP application."""
    try:
        data = client.get(f"/apps/{id}")
        print_json(data)
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("credentials")
def get_credentials(
    id: int = typer.Argument(..., help="Application ID"),
    namespace: str = typer.Option(..., "--namespace", "-n", help="Kubernetes namespace where the app is deployed"),
):
    """Get PostgreSQL credentials for a CNP application."""
    try:
        data = client.get(f"/apps/{id}/services/postgresql/credentials", params={"namespace": namespace})
        print_table(
            "PostgreSQL credentials",
            ["Field", "Value"],
            [
                ["host", data["host"]],
                ["port", data["port"]],
                ["username", data["username"]],
                ["password", data["password"]],
                ["database", data["database"]],
                ["DATABASE_URL", data["database_url"]],
            ],
        )
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("delete")
def delete_app(
    id: int = typer.Argument(..., help="Application ID"),
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Skip confirmation prompt"),
):
    """Delete a CNP application."""
    if not confirm:
        typer.confirm(f"Delete application {id}?", abort=True)
    try:
        client.delete(f"/apps/{id}")
        print_success(f"Application {id} deleted.")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("members")
def list_members(
    id: int = typer.Argument(..., help="Application ID"),
):
    """List members of a CNP application (requires Maintainer+)."""
    try:
        data = client.get(f"/apps/{id}/members")
        if not data:
            typer.echo("No members found.")
            return
        print_table(
            f"Members — app {id}",
            ["CNP User ID", "Display Name", "Access Level", "Tier", "Status"],
            [
                [
                    m.get("cnp_user_id") or "—",
                    m.get("display_name") or "—",
                    m.get("access_level"),
                    m.get("tier_cnp"),
                    m.get("status"),
                ]
                for m in data
            ],
        )
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("add-member")
def add_member(
    id: int = typer.Argument(..., help="Application ID"),
    gitlab_user_id: int = typer.Option(..., "--gitlab-user-id", "-u", help="GitLab numeric user ID"),
    access_level: int = typer.Option(30, "--access-level", "-a", help="Access level (10=Guest, 30=Developer, 40=Maintainer, 50=Owner)"),
):
    """Add a GitLab user to an app project (write-through, requires Maintainer+)."""
    try:
        data = client.post(f"/apps/{id}/members", json={"gitlab_user_id": gitlab_user_id, "access_level": access_level})
        print_success(f"Member added — tier: {data.get('tier_cnp')}, status: {data.get('status')}")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("invite")
def invite_member(
    id: int = typer.Argument(..., help="Application ID"),
    email: str = typer.Option(..., "--email", "-e", help="Email address to invite"),
    access_level: int = typer.Option(30, "--access-level", "-a", help="Access level (10=Guest, 30=Developer, 40=Maintainer, 50=Owner)"),
):
    """Invite a user by email to an app project (write-through, requires Maintainer+)."""
    try:
        data = client.post(f"/apps/{id}/invitations", json={"email": email, "access_level": access_level})
        print_success(f"Invitation sent to {email} — tier: {data.get('tier_cnp')}, status: {data.get('status')}")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("access")
def my_access(
    id: int = typer.Argument(..., help="Application ID"),
):
    """Show your effective access tier on a CNP application."""
    try:
        data = client.get(f"/apps/{id}/my-access")
        tier = data.get("tier", "—")
        is_admin = data.get("is_admin", False)
        console.print(f"Tier: [bold]{tier}[/bold]" + ("  [yellow](admin override)[/yellow]" if is_admin else ""))
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


# ── CNP Doctor ────────────────────────────────────────────────────────────────
# Lecture seule : la commande appelle POST /apps/{id}/doctor/diagnose et affiche le
# diagnostic. Elle n'exécute jamais l'action conseillée : un rollback se confirme
# dans l'interface web, avec les droits de la route existante.


class DoctorEnv(str, Enum):
    prod = "prod"
    dev = "dev"


class DoctorOutput(str, Enum):
    text = "text"
    json = "json"


# Libellé et couleur de chaque verdict : rouge pour une panne, jaune pour un état à
# surveiller, cyan pour un état sans panne de l'application, vert quand tout va bien.
_DOCTOR_VERDICTS = {
    "regression": ("Régression après un déploiement", "bold red"),
    "failing": ("En panne", "bold red"),
    "unstable": ("Instable", "bold yellow"),
    "ci_failure": ("Dernier pipeline en échec", "bold yellow"),
    "cluster_offline": ("Cluster hors ligne", "bold yellow"),
    "inconclusive": ("Signaux insuffisants", "bold yellow"),
    "deploying": ("Déploiement en cours", "bold cyan"),
    "stopped": ("Environnement arrêté", "bold cyan"),
    "not_deployed": ("Pas encore déployée", "bold cyan"),
    "healthy": ("Application saine", "bold green"),
}

_DOCTOR_SOURCES = {
    "ai": "IA encadrée",
    "rules": "Sans IA",
    "rules_fallback": "IA indisponible — diagnostic établi par la plateforme",
}

_DOCTOR_AI_ERRORS = {
    "quota": "quota du fournisseur IA atteint",
    "provider_error": "fournisseur IA en erreur ou non configuré",
    "unreachable": "fournisseur IA injoignable",
    "limit": "limite d'usage IA de la plateforme atteinte",
}

_DOCTOR_FILE_CHANGES = {
    "added": "ajouté",
    "modified": "modifié",
    "deleted": "supprimé",
    "renamed": "renommé",
}


def _doctor_time(value: str | None) -> str:
    """Horodatage ISO de l'API → « 16/11 15:01 », à l'heure locale du poste."""
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return str(value)


def _doctor_duration(seconds: float | None) -> str:
    """Même découpage que la plateforme : « 45 s », « 1 min », « 3 h », « 3 jours »."""
    s = max(0, int(seconds or 0))
    if s < 60:
        return f"{s} s"
    if s < 90:
        return "1 min"
    if s < 90 * 60:
        return f"{round(s / 60)} min"
    if s < 36 * 3600:
        return f"{round(s / 3600)} h"
    days = round(s / 86400)
    return f"{days} jour{'s' if days > 1 else ''}"


def _say(*parts, indent: int = 0, hang: int = 0, wrap: bool = True) -> None:
    """Une ligne de sortie, repliée à la largeur du terminal ; les lignes de suite sont
    décalées de `hang` espaces.

    Les données (logs, titres de commits) passent en `Text` : Rich n'y interprète ni
    balisage ni emoji. `wrap=False` laisse la ligne entière (liens), pour qu'un lien
    reste copiable et cliquable."""
    text = Text.assemble(*parts)
    lines = text.wrap(console, max(20, console.width - indent - hang)) if wrap else [text]
    for i, line in enumerate(lines):
        line.rstrip()
        console.print(Text.assemble(" " * (indent + (hang if i else 0)), line), soft_wrap=True)


def _doctor_section(title: str) -> None:
    console.print()
    _say((title, "bold"))


def _doctor_source(d: dict) -> str:
    source = d.get("source") or "?"
    label = _DOCTOR_SOURCES.get(source, source)
    ai = d.get("ai") or {}
    if source == "ai" and ai.get("model"):
        return f"{label} ({ai.get('provider') or '?'} · {ai['model']})"
    if source == "rules_fallback" and ai.get("error"):
        return f"{label} ({_DOCTOR_AI_ERRORS.get(ai['error'], ai['error'])})"
    return label


def _doctor_evidence(evidence: list) -> None:
    if not evidence:
        return
    cited = [e for e in evidence if e.get("cited")]
    _doctor_section("Preuves citées")
    if not cited:
        _say("Aucune preuve citée.", indent=2)
    for e in cited:
        when = _doctor_time(e.get("at"))
        _say((f"[{e.get('id')}] ", "bold"), (f"{when} · " if when else "", "dim"), e.get("label") or "",
             indent=2, hang=5)
        if e.get("detail"):
            _say((e["detail"], "dim"), indent=7)
        if e.get("url"):
            _say((e["url"], "dim"), indent=7, wrap=False)
    others = len(evidence) - len(cited)
    if others:
        what = "autre signal collecté, non cité" if others == 1 else "autres signaux collectés, non cités"
        _say((f"+ {others} {what} (--output json pour le détail)", "dim"), indent=2)


def _doctor_timeline(t: dict) -> None:
    _doctor_section("Chronologie")
    last_healthy = t.get("last_healthy") or {}
    for e in t.get("entries") or []:
        marks = []
        if e.get("suspect"):
            marks.append(("  [déploiement suspect]", "bold red"))
        elif e.get("healthy") is True:
            ran = ""
            if last_healthy.get("ran_for_seconds") and last_healthy.get("history_id") == e.get("history_id"):
                ran = f", en service pendant {_doctor_duration(last_healthy['ran_for_seconds'])}"
            marks.append((f"  [dernière version saine{ran}]", "bold green"))
        elif e.get("healthy") is False:
            marks.append(("  [version en panne]", "yellow"))
        _say((f"{_doctor_time(e.get('at')):<13}", "dim"), e.get("label") or e.get("kind") or "", *marks,
             indent=2, hang=13)

    delay, correlation = t.get("onset_delay_seconds"), t.get("correlation")
    if correlation and delay is not None:
        _say(f"Panne apparue {_doctor_duration(delay)} après le déploiement suspect · corrélation {correlation}",
             indent=2)
    elif delay is not None:
        _say(f"Premier signal d'échec {_doctor_duration(delay)} après le dernier déploiement : "
             "aucune corrélation retenue.", indent=2)
    elif not correlation:
        _say("Aucun déploiement récent n'est corrélé à la panne.", indent=2)


def _doctor_changes(c: dict) -> None:
    _doctor_section(f"Ce qui a changé ({c.get('from_revision') or '?'} → {c.get('to_revision') or '?'})")
    if c.get("unavailable_reason"):
        _say(("Comparaison indisponible : ", "yellow"), c["unavailable_reason"], indent=2)
        return
    commits, files = c.get("commits") or [], c.get("files") or []
    if not commits and not files:
        _say("Aucun commit trouvé entre les deux versions.", indent=2)
    for commit in commits:
        author = commit.get("author")
        _say((f"{(commit.get('sha') or '')[:8]}  ", "bold"), commit.get("title") or "",
             (f"  ({author})" if author else "", "dim"), indent=2, hang=10)
    if files:
        _say(f"{len(files)} fichier{'s' if len(files) > 1 else ''} modifié{'s' if len(files) > 1 else ''} :",
             indent=2)
        for f in files:
            change = f.get("change") or ""
            _say((f"{_DOCTOR_FILE_CHANGES.get(change, change):<9}", "dim"), f.get("path") or "", indent=4)
    if c.get("truncated"):
        _say(("Liste tronquée par la plateforme (20 commits et 50 fichiers au plus).", "dim"), indent=2)
    if c.get("compare_url"):
        _say(("Comparer : ", "dim"), c["compare_url"], indent=2, wrap=False)


def _doctor_actions(actions: list) -> None:
    if not actions:
        return
    _doctor_section("Actions conseillées")
    for i, a in enumerate(actions, 1):
        tags = []
        if a.get("primary"):
            tags.append(("  (principale)", "bold"))
        if not a.get("allowed", True):
            tags.append((f"  [non autorisée : rôle {a.get('required_role') or '?'} requis]", "yellow"))
        _say(f"{i}. ", (a.get("label") or a.get("kind") or "", "bold"), *tags, indent=2, hang=3)
        if a.get("description"):
            _say(a["description"], indent=5)
        if a.get("url"):
            _say((a["url"], "dim"), indent=5, wrap=False)


def _doctor_how_to_apply(d: dict) -> str:
    """Dernière ligne : la CLI n'exécute rien, et voici où appliquer l'action principale."""
    note = "La CLI n'exécute aucune action."
    actions = d.get("actions") or []
    primary = next((a for a in actions if a.get("primary")), actions[0] if actions else None)
    if primary is None:
        return note
    params = primary.get("params") or {}
    env = params.get("env") or d.get("env") or "prod"
    kind = primary.get("kind")
    if kind == "rollback":
        rev = params.get("revision") or "?"
        step = (f"Pour revenir à la version {rev} en {env} : interface web, onglet History de "
                f"l'application, révision {rev}, Rollback puis Confirm (ou bouton de la carte "
                "CNP Doctor, onglet Overview).")
    elif kind == "resume":
        step = f"Pour relancer l'environnement {env} : interface web, onglet Overview, Resume."
    elif kind == "view_logs":
        step = f"Pour lire les erreurs complètes : interface web, onglet Logs de l'application ({env})."
    elif kind == "view_history":
        step = "Pour voir les déploiements : interface web, onglet History de l'application."
    elif kind in ("open_pipeline", "open_repo_compare") and primary.get("url"):
        step = "Pour continuer : ouvrir le lien de l'action principale ci-dessus."
    elif kind == "retry_later":
        step = f"Relancer « cnp app doctor {d.get('app_id')} --env {env} » dans une minute."
    elif kind == "contact_maintainer":
        step = "Prévenir un administrateur de la plateforme."
    else:
        step = f"Action conseillée : {primary.get('label') or kind}."
    role = primary.get("required_role")
    if role and not primary.get("allowed", True):
        step += f" Rôle {role} requis : à demander à un {role}."
    return f"{note} {step}"


def _doctor_render(d: dict) -> None:
    verdict = d.get("verdict") or "?"
    label, style = _DOCTOR_VERDICTS.get(verdict, (verdict, "bold"))
    _say(("CNP Doctor", "bold"),
         f" — {d.get('app_name') or d.get('app_id')} ({d.get('env') or '?'})"
         f" · {_doctor_time(d.get('generated_at'))} · rôle {d.get('user_role') or '?'}")
    console.print()
    _say((label, style))
    _say(d.get("headline") or "")
    _say(("Source : ", "dim"), _doctor_source(d))

    cause = d.get("cause")
    if cause:
        _doctor_section("Cause probable")
        _say(cause.get("summary") or "", (f" (confiance {cause.get('confidence') or '?'})", "bold"), indent=2)
    if d.get("explanation"):
        _doctor_section("Explication")
        _say(d["explanation"], indent=2)

    _doctor_evidence(d.get("evidence") or [])
    if d.get("timeline"):
        _doctor_timeline(d["timeline"])
    if d.get("changes"):
        _doctor_changes(d["changes"])
    _doctor_actions(d.get("actions") or [])

    missing = d.get("missing_signals") or []
    if missing:
        _doctor_section("Signaux manquants")
        for m in missing:
            _say((f"{m.get('source') or '?'} : ", "bold"), m.get("reason") or "", indent=2)
    if d.get("raw_text"):
        _doctor_section("Réponse brute de l'IA (non structurée)")
        _say((d["raw_text"], "dim"), indent=2)

    console.print()
    _say((_doctor_how_to_apply(d), "bold"))


@app.command("doctor")
def doctor(
    id: Annotated[int, typer.Argument(help="Application ID")],
    env: Annotated[DoctorEnv, typer.Option("--env", "-e", help="Environment to diagnose: prod or dev")] = DoctorEnv.prod,
    output: Annotated[DoctorOutput, typer.Option("--output", "-o", help="Output format: text or json")] = DoctorOutput.text,
):
    """Diagnose an application environment with CNP Doctor (read-only, never executes an action)."""
    try:
        data = client.post(f"/apps/{id}/doctor/diagnose", json={"env": env.value})
    except Exception as e:  # noqa: BLE001 — le client lève une Exception portant le `detail` de l'API
        print_error(str(e))
        raise typer.Exit(1)

    if output == DoctorOutput.json:
        typer.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return
    _doctor_render(data)
