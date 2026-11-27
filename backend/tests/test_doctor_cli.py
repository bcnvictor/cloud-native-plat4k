"""CLI `cnp app doctor` — affichage du diagnostic CNP Doctor (lecture seule).

Les diagnostics d'exemple reprennent ceux de `frontend-new/src/__fixtures__/doctor.ts`
(application demo-shop, version saine a1b2c3d4, version en panne f4e5d6c7).
"""
import copy
import json

import pytest

# La CLI dépend de typer, rich et toml (extra `test` de backend/pyproject.toml,
# requirements-dev.lock). Un virtualenv installé sans ces paquets saute ces tests au
# lieu d'échouer à la collecte.
pytest.importorskip("typer")
pytest.importorskip("rich")
pytest.importorskip("toml")

from typer.testing import CliRunner  # noqa: E402

AI_USED = {
    "used": True, "provider": "gemini", "model": "gemini-flash-latest",
    "input_tokens": 1840, "output_tokens": 260, "estimated_cost_usd": 0.0009, "error": None,
}
AI_UNUSED = {
    "used": False, "provider": None, "model": None,
    "input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": None, "error": None,
}

REGRESSION = {
    "app_id": 7,
    "app_name": "demo-shop",
    "env": "prod",
    "generated_at": "2026-11-16T14:07:31Z",
    "verdict": "regression",
    "source": "ai",
    "headline": "demo-shop redémarre en boucle en prod depuis le déploiement de 14 h 01.",
    "explanation": (
        "La version f4e5d6c7 plante au démarrage : elle attend la variable PAYMENT_API_URL, "
        "absente de la configuration. La version précédente a1b2c3d4 a tourné 3 jours sans incident."
    ),
    "cause": {
        "summary": "Le dernier déploiement lit une variable de configuration qui n'existe pas (PAYMENT_API_URL).",
        "confidence": "haute",
        "category": "deployment",
    },
    "evidence": [
        {"id": "E1", "source": "kubernetes", "label": "Pod demo-shop-7d9f8b6c5-x2k4q : CrashLoopBackOff, 6 redémarrages",
         "detail": "Dernier arrêt : Error (code 1) à 14:06:48. Back-off restarting failed container.",
         "at": "2026-11-16T14:02:11Z", "url": None, "cited": True},
        # Une ligne de log contient des crochets : la sortie ne doit pas les prendre pour du balisage Rich.
        {"id": "E2", "source": "logs", "label": "KeyError: 'PAYMENT_API_URL' (×6 sur la dernière heure)",
         "detail": "14:02:10 [ERROR] KeyError: 'PAYMENT_API_URL'\n14:02:10 [error] Application startup failed.",
         "at": "2026-11-16T14:02:10Z", "url": None, "cited": True},
        {"id": "E3", "source": "deployments", "label": "Déploiement de f4e5d6c7 en prod à 14:01, 1 minute avant la panne",
         "detail": None, "at": "2026-11-16T14:01:02Z", "url": None, "cited": True},
        {"id": "E4", "source": "argocd", "label": "ArgoCD : sync Synced, santé Degraded",
         "detail": None, "at": "2026-11-16T14:05:00Z", "url": None, "cited": False},
        {"id": "E5", "source": "git", "label": "Commit f4e5d6c7 : « feat(payment): nouveau client de paiement »",
         "detail": "Fichiers modifiés : app/config.py, app/payment/client.py, requirements.txt",
         "at": "2026-11-16T13:52:40Z",
         "url": "https://gitlab.example.com/cnp-apps/team-demo/demo-shop/-/commit/f4e5d6c7", "cited": True},
        {"id": "E6", "source": "ci", "label": "Dernier pipeline #482 : success (branche main)",
         "detail": None, "at": "2026-11-16T13:58:12Z",
         "url": "https://gitlab.example.com/cnp-apps/team-demo/demo-shop/-/pipelines/482", "cited": False},
    ],
    "timeline": {
        "entries": [
            {"at": "2026-11-13T13:20:00Z", "kind": "deployment", "label": "Déploiement de a1b2c3d4",
             "revision": "a1b2c3d4", "history_id": 11, "suspect": False, "healthy": True},
            {"at": "2026-11-16T14:01:02Z", "kind": "deployment", "label": "Déploiement de f4e5d6c7",
             "revision": "f4e5d6c7", "history_id": 12, "suspect": True, "healthy": False},
            {"at": "2026-11-16T14:02:10Z", "kind": "failure_onset", "label": "Premier redémarrage du conteneur",
             "revision": None, "history_id": None, "suspect": False, "healthy": None},
            {"at": "2026-11-16T14:05:00Z", "kind": "degraded", "label": "Application marquée dégradée",
             "revision": None, "history_id": None, "suspect": False, "healthy": None},
        ],
        "suspect": {"history_id": 12, "revision": "f4e5d6c7", "deployed_at": "2026-11-16T14:01:02Z",
                    "ran_for_seconds": None},
        "last_healthy": {"history_id": 11, "revision": "a1b2c3d4", "deployed_at": "2026-11-13T13:20:00Z",
                         "ran_for_seconds": 261662},
        "onset_at": "2026-11-16T14:02:10Z",
        "onset_delay_seconds": 68,
        "correlation": "haute",
    },
    "changes": {
        "from_revision": "a1b2c3d4",
        "to_revision": "f4e5d6c7",
        "compare_url": "https://gitlab.example.com/cnp-apps/team-demo/demo-shop/-/compare/a1b2c3d4...f4e5d6c7",
        "commits": [
            {"sha": "f4e5d6c7", "title": "feat(payment): nouveau client de paiement", "author": "Alice Martin",
             "at": "2026-11-16T13:52:40Z",
             "url": "https://gitlab.example.com/cnp-apps/team-demo/demo-shop/-/commit/f4e5d6c7"},
            {"sha": "9c8b7a6d", "title": "chore: mise à jour des dépendances", "author": "Alice Martin",
             "at": "2026-11-16T11:14:03Z",
             "url": "https://gitlab.example.com/cnp-apps/team-demo/demo-shop/-/commit/9c8b7a6d"},
        ],
        "files": [
            {"path": "app/config.py", "change": "modified"},
            {"path": "app/payment/client.py", "change": "added"},
            {"path": "requirements.txt", "change": "modified"},
        ],
        "truncated": False,
        "unavailable_reason": None,
    },
    "actions": [
        {"id": "A1", "kind": "rollback", "label": "Revenir à la version a1b2c3d4",
         "description": "Dernière version saine : elle a tourné 3 jours sans incident.",
         "primary": True, "allowed": True, "required_role": "maintainer",
         "params": {"env": "prod", "history_id": 11, "revision": "a1b2c3d4"}, "url": None},
        {"id": "A2", "kind": "open_repo_compare", "label": "Voir ce qui a changé sur GitLab",
         "description": "Comparer a1b2c3d4 et f4e5d6c7 pour corriger le commit.",
         "primary": False, "allowed": True, "required_role": None, "params": {},
         "url": "https://gitlab.example.com/cnp-apps/team-demo/demo-shop/-/compare/a1b2c3d4...f4e5d6c7"},
        {"id": "A3", "kind": "view_logs", "label": "Voir les logs",
         "description": "Lire les erreurs complètes dans l'onglet Logs.",
         "primary": False, "allowed": True, "required_role": None, "params": {"env": "prod"}, "url": None},
    ],
    "missing_signals": [],
    "raw_text": None,
    "ai": AI_USED,
    "user_role": "maintainer",
}

HEALTHY = {
    "app_id": 7,
    "app_name": "demo-shop",
    "env": "prod",
    "generated_at": "2026-11-16T15:10:00Z",
    "verdict": "healthy",
    "source": "rules",
    "headline": "demo-shop fonctionne normalement en prod : rien à signaler.",
    "explanation": None,
    "cause": None,
    "evidence": [
        {"id": "E1", "source": "argocd", "label": "ArgoCD : sync Synced, santé Healthy", "detail": None,
         "at": "2026-11-16T15:09:40Z", "url": None, "cited": True},
        {"id": "E2", "source": "kubernetes", "label": "2/2 réplicas prêts, aucun redémarrage", "detail": None,
         "at": None, "url": None, "cited": True},
    ],
    "timeline": None,
    "changes": None,
    "actions": [],
    "missing_signals": [],
    "raw_text": None,
    "ai": AI_UNUSED,
    "user_role": "developer",
}

DIAGNOSE_PATH = "/apps/7/doctor/diagnose"


def _regression_as_developer() -> dict:
    d = copy.deepcopy(REGRESSION)
    d["user_role"] = "developer"
    for a in d["actions"]:
        if a["kind"] == "rollback":
            a["allowed"] = False
    return d


def _fallback() -> dict:
    d = copy.deepcopy(REGRESSION)
    d["source"] = "rules_fallback"
    d["explanation"] = None
    d["cause"] = {
        "summary": "Régression probable du dernier déploiement : la panne a commencé 1 min après.",
        "confidence": "haute", "category": "deployment",
    }
    d["ai"] = dict(AI_UNUSED, provider="gemini", model="gemini-flash-latest", error="quota")
    return d


def _flat(text: str) -> str:
    """Rich coupe les lignes à la largeur du terminal : on compare le texte sans ses retours."""
    return " ".join(text.split())


@pytest.fixture
def doctor_cli(monkeypatch, tmp_path):
    """La commande avec un client HTTP simulé qui enregistre chaque appel.

    `response` est ce que renvoie la route de diagnostic ; une Exception est levée telle
    quelle, comme le fait `APIClient._handle_response` sur une erreur HTTP.
    """
    import cli.core.config as config
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.toml")
    from cli.commands import apps

    state = {"response": copy.deepcopy(REGRESSION), "calls": []}

    def post(path, json=None, data=None):
        state["calls"].append(("POST", path, json))
        if isinstance(state["response"], Exception):
            raise state["response"]
        return state["response"]

    def forbidden(method):
        def call(path, *args, **kwargs):
            state["calls"].append((method, path, kwargs.get("json")))
            raise AssertionError(f"unexpected {method} {path}")
        return call

    monkeypatch.setattr(apps.client, "post", post)
    for method in ("get", "put", "delete"):
        monkeypatch.setattr(apps.client, method, forbidden(method.upper()))
    # Filet : aucune requête réelle ne doit partir, même en contournant les méthodes ci-dessus.
    monkeypatch.setattr(apps.client.session, "request", forbidden("SESSION"))

    def run(*args):
        return CliRunner().invoke(apps.app, ["doctor", *args])

    return run, state


def test_regression_text_shows_every_part_of_the_diagnosis(doctor_cli):
    run, state = doctor_cli
    result = run("7")
    assert result.exit_code == 0, result.output
    out = _flat(result.stdout)

    # Verdict, constat, source, cause et confiance.
    assert "Regression after a deployment" in out
    assert "demo-shop redémarre en boucle en prod depuis le déploiement de 14 h 01." in out
    assert "Guided AI" in out
    assert "PAYMENT_API_URL" in out and "(high confidence)" in out
    # Preuves citées (détail compris, crochets des logs intacts), signaux non cités comptés.
    assert "[E1]" in out and "Pod demo-shop-7d9f8b6c5-x2k4q : CrashLoopBackOff, 6 redémarrages" in out
    assert "14:02:10 [ERROR] KeyError" in out and "[error] Application startup failed." in out
    assert "[E4]" not in out
    assert "+ 2 other signals collected, not cited" in out
    # Chronologie : déploiement suspect, dernière version saine, délai et corrélation.
    assert "Déploiement de f4e5d6c7 [suspect deployment]" in out
    assert "Déploiement de a1b2c3d4 [last healthy version, in service for 3 days]" in out
    assert "Failure appeared 1 min after the suspect deployment · high correlation" in out
    # Ce qui a changé.
    assert "What changed (a1b2c3d4 → f4e5d6c7)" in out
    assert "feat(payment): nouveau client de paiement" in out
    assert "added app/payment/client.py" in out
    assert "compare/a1b2c3d4...f4e5d6c7" in out
    # Actions, dans l'ordre, et la dernière ligne : rien n'est exécuté.
    assert out.index("1. Revenir à la version a1b2c3d4 (primary)") < out.index("2. Voir ce qui a changé")
    assert "The CLI does not run any action." in out
    assert "History tab of the application, revision a1b2c3d4" in out

    assert state["calls"] == [("POST", DIAGNOSE_PATH, {"env": "prod"})]


def test_developer_sees_the_rollback_with_the_required_role(doctor_cli):
    run, state = doctor_cli
    state["response"] = _regression_as_developer()
    result = run("7")
    assert result.exit_code == 0, result.output
    out = _flat(result.stdout)
    assert "Revenir à la version a1b2c3d4 (primary) [not allowed: maintainer role required]" in out
    assert "ask a maintainer" in out


def test_fallback_says_the_ai_did_not_answer(doctor_cli):
    run, state = doctor_cli
    state["response"] = _fallback()
    result = run("7")
    assert result.exit_code == 0, result.output
    out = _flat(result.stdout)
    assert "AI unavailable — diagnosis based on platform rules (AI provider quota reached)" in out
    assert "Régression probable du dernier déploiement" in out
    assert "Revenir à la version a1b2c3d4" in out


def test_obvious_case_is_answered_without_ai(doctor_cli):
    run, state = doctor_cli
    state["response"] = copy.deepcopy(HEALTHY)
    result = run("7")
    assert result.exit_code == 0, result.output
    out = _flat(result.stdout)
    assert "Healthy application" in out
    assert "No AI" in out
    assert "Probable cause" not in out and "Timeline" not in out
    assert "The CLI does not run any action." in out


def test_unavailable_comparison_and_missing_signals_are_shown(doctor_cli):
    run, state = doctor_cli
    d = copy.deepcopy(REGRESSION)
    d["changes"].update(commits=[], files=[], compare_url=None,
                        unavailable_reason="Comparaison GitLab indisponible (403).")
    d["missing_signals"] = [{"source": "logs", "reason": "Loki injoignable (délai dépassé)."}]
    state["response"] = d
    result = run("7")
    assert result.exit_code == 0, result.output
    out = _flat(result.stdout)
    assert "Comparison unavailable: Comparaison GitLab indisponible (403)." in out
    assert "Missing signals" in out and "logs: Loki injoignable (délai dépassé)." in out


def test_json_output_is_the_raw_diagnosis(doctor_cli):
    run, state = doctor_cli
    result = run("7", "--env", "dev", "--output", "json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == REGRESSION
    assert state["calls"] == [("POST", DIAGNOSE_PATH, {"env": "dev"})]


def test_invalid_env_is_refused_before_any_call(doctor_cli):
    run, state = doctor_cli
    result = run("7", "--env", "staging")
    assert result.exit_code != 0
    assert state["calls"] == []


def test_invalid_output_is_refused_before_any_call(doctor_cli):
    run, state = doctor_cli
    result = run("7", "--output", "yaml")
    assert result.exit_code != 0
    assert state["calls"] == []


def test_forbidden_exits_nonzero_with_the_api_message(doctor_cli):
    run, state = doctor_cli
    message = "Le diagnostic est réservé aux rôles developer et supérieurs sur cette application."
    state["response"] = Exception(f"Error: {message}")
    result = run("7", "-e", "dev")
    assert result.exit_code == 1
    assert message in _flat(result.stdout)
    assert state["calls"] == [("POST", DIAGNOSE_PATH, {"env": "dev"})]


def test_only_the_diagnose_route_is_ever_called(doctor_cli):
    """Le Doctor n'exécute rien : ni rollback, ni resume, ni aucune autre route."""
    run, state = doctor_cli
    for response in (REGRESSION, _regression_as_developer(), _fallback(), HEALTHY):
        state["response"] = copy.deepcopy(response)
        for output in ("text", "json"):
            assert run("7", "-o", output).exit_code == 0
    assert {(method, path) for method, path, _ in state["calls"]} == {("POST", DIAGNOSE_PATH)}
