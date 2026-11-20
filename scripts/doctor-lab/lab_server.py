#!/usr/bin/env python3
"""Labo CNP Doctor : serveur simulé à état (bibliothèque standard uniquement).

Un seul processus et un seul port (9000 par défaut) imitent tout ce que le
backend lit pendant un diagnostic, sans aucun cluster ni service réel :

    /loki/api/v1/query_range              Loki : logs de l'application
    /argocd/api/v1/applications/{name}    ArgoCD : sync, santé, image, historique
    /k8s/...                              API Kubernetes : namespaces, deployment, pods, events
    /gitlab/api/v4/...                    API GitLab : projets, pipelines, jobs, compare, fichiers
    /llm/v1/chat/completions              fournisseur IA compatible OpenAI
    /prometheus/api/v1/...                Prometheus vide (les pages FinOps s'affichent sans erreur)
    /lab-gitlab/...                       pages HTML derrière les liens « GitLab » de la carte
    /lab/state  /lab/break  /lab/ci-failure  /lab/reset   pilotage du scénario

Scénario, environnement prod de l'application demo-shop :

    healthy      la version a1b2c3d4 tourne depuis 3 jours, tout va bien.
    broken       POST /lab/break : la version f4e5d6c7 est déployée en prod et plante
                 à chaque démarrage (variable PAYMENT_API_URL absente).
    rolled_back  le backend réécrit image.tag dans values-prod.yaml du dépôt GitOps
                 simulé (rollback confirmé dans l'interface) : la prod revient à
                 la version choisie et redevient saine.
    ci_failure   POST /lab/ci-failure : l'application tourne normalement, mais le
                 dernier pipeline a échoué sur le job « test ».

L'environnement dev reste sain : f4e5d6c7 y tourne, PAYMENT_API_URL y est définie.

Usage :
    python3 scripts/doctor-lab/lab_server.py [port]

Variables d'environnement :
    LAB_BIND        adresse d'écoute (défaut 0.0.0.0, nécessaire dans le conteneur)
    LAB_PUBLIC_URL  adresse du serveur vue par le navigateur, pour les liens
                    GitLab de la carte (défaut http://localhost:9009)

Tout est inventé ; les horodatages sont calculés par rapport à « maintenant ».
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

# ── Données du scénario ───────────────────────────────────────────────────────

APP = "demo-shop"                       # nom de l'app = nom du Deployment = container
APP_PROJECT_ID = 4242                   # projet GitLab de l'application
APP_PROJECT_PATH = "team-demo/demo-shop"
GITOPS_PROJECT_ID = 4300                # dépôt GitOps (GITOPS_REPO_URL du backend)
GITOPS_PROJECT_PATH = "lab-platform/cnp-gitops"
REGISTRY = "registry.lab.local/team-demo/demo-shop"
NAMESPACES = ("prod", "dev")
REPLICAS = {"prod": 2, "dev": 1}

# Commits de l'application, du plus ancien au plus récent. Le tag d'image d'une
# version = les 8 premiers caractères de son commit (convention CNP).
SHA_OLD = "7c3e9a15d2b84f601e7a9c3b5f2d8e4a6b0c1d93"
SHA_GOOD = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
SHA_REFACTOR = "e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0"
SHA_BAD = "f4e5d6c70a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d"
SHA_CI = "5d4c3b2a19f8e7d6c5b4a3928170f6e5d4c3b2a1"
CHAIN = (SHA_OLD, SHA_GOOD, SHA_REFACTOR, SHA_BAD, SHA_CI)
SHAS = {sha[:8]: sha for sha in CHAIN}
GOOD, BAD = SHA_GOOD[:8], SHA_BAD[:8]

MIN, HOUR, DAY = 60, 3600, 86400

# La panne simule un déploiement survenu 3 minutes avant le clic : la boucle de
# crash a déjà un historique (redémarrages, événements, logs) quand on lance le
# diagnostic. Le premier signal d'échec tombe environ 1 min après le déploiement.
BREAK_BACKDATE_S = 3 * MIN
POD_STOP_S = 8           # arrêt des anciens pods après le déploiement
POD_PULL_S = 52          # ordonnancement + téléchargement de l'image avant le 1er démarrage
RUN_S = 3                # durée de vie d'un conteneur avant le crash
BACKOFFS = (10, 20, 40, 80, 160)   # attente du kubelet entre deux redémarrages, puis 300 s

# Faux jeton, assemblé à l'exécution pour qu'aucun littéral ressemblant à un
# jeton ne soit commité. Il apparaît dans une ligne de log d'erreur : la carte
# du Doctor doit l'afficher masqué ([REDACTED:gitlab-token]).
FAKE_TOKEN = "gl" + "pat-" + "LAB" + "0d0c7012345678abcdef"

PUBLIC_URL = os.environ.get("LAB_PUBLIC_URL", "http://localhost:9009").rstrip("/")
APP_WEB_URL = f"{PUBLIC_URL}/lab-gitlab/{APP_PROJECT_PATH}"
GITOPS_WEB_URL = f"{PUBLIC_URL}/lab-gitlab/{GITOPS_PROJECT_PATH}"

COMMITS = {
    SHA_OLD: ("fix(cart): arrondi des totaux au centime", "Camille Robert", 10 * DAY + HOUR,
              [("app/cart.py", "modified")]),
    SHA_GOOD: ("feat(catalog): pagination de la liste des produits", "Inès Martin", 3 * DAY + HOUR,
               [("app/catalog.py", "modified"), ("tests/test_catalog.py", "modified")]),
    SHA_REFACTOR: ("refactor(config): centraliser la lecture des variables d'environnement",
                   "Inès Martin", 26 * HOUR, [("app/config.py", "modified")]),
    SHA_BAD: ("feat(payment): brancher le nouveau prestataire de paiement", "Lucas Bernard", 21 * HOUR,
              [("app/config.py", "modified"), ("app/payment/client.py", "added"),
               ("requirements.txt", "modified")]),
    SHA_CI: ("feat(cart): codes promo cumulables", "Lucas Bernard", 9 * MIN,
             [("app/cart.py", "modified"), ("tests/test_cart.py", "modified")]),
}

# ReplicaSets : un hash de template par version d'image (un rollback réutilise
# l'ancien ReplicaSet, comme Kubernetes).
RS_HASH = {SHA_OLD[:8]: "5f7d9b8c6", GOOD: "6d8f7c9b5", BAD: "85c4d9f6b"}
POD_SUFFIXES = {
    ("prod", "initial"): ("x2kqp", "m7wzt"),
    ("prod", "broken"): ("q9rtn", "h4vzl"),
    ("prod", "rolled_back"): ("p3jdx", "w8nfk"),
    ("dev", "initial"): ("k2v7s",),
}

ACCESS_LINES = (
    'INFO:     10.42.1.7:51234 - "GET /api/products?page=1 HTTP/1.1" 200 OK',
    'INFO:     10.42.0.1:40112 - "GET /healthz HTTP/1.1" 200 OK',
    'INFO:     10.42.1.7:51302 - "GET /api/products/TSHIRT-01 HTTP/1.1" 200 OK',
    'INFO:     10.42.1.7:51318 - "POST /api/cart/items HTTP/1.1" 201 Created',
    'INFO:     10.42.0.1:40118 - "GET /healthz HTTP/1.1" 200 OK',
    'INFO:     10.42.1.7:51377 - "GET /api/cart HTTP/1.1" 200 OK',
    "INFO:     app.orders: commande 10482 validée (3 articles, 74,90 €)",
    'INFO:     10.42.1.7:51402 - "POST /api/checkout HTTP/1.1" 200 OK',
)
STARTUP_LINES = (
    "INFO:     Started server process [1]",
    "INFO:     Waiting for application startup.",
    "INFO:     Application startup complete.",
    "INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)",
)
SHUTDOWN_LINES = (
    "INFO:     Shutting down",
    "INFO:     Waiting for application shutdown.",
    "INFO:     Application shutdown complete.",
    "INFO:     Finished server process [1]",
)
# Trace Python de la version f4e5d6c7 au démarrage. Ces lignes de suite de trace
# n'ont pas de niveau (le backend les lit comme INFO) ; seules la dernière ligne
# de l'exception et l'arrêt d'uvicorn sont classées ERROR par le pipeline de logs.
TRACEBACK_LINES = (
    "Traceback (most recent call last):",
    '  File "/usr/local/lib/python3.11/site-packages/starlette/routing.py", line 693, in lifespan',
    "    async with self.lifespan_context(app) as maybe_state:",
    '  File "/app/app/main.py", line 27, in lifespan',
    "    app.state.payments = PaymentClient.from_settings(settings)",
    '  File "/app/app/payment/client.py", line 34, in from_settings',
    "    base_url=settings.payment_api_url,",
    '  File "/app/app/config.py", line 48, in payment_api_url',
    '    return os.environ["PAYMENT_API_URL"]',
    '  File "<frozen os>", line 714, in __getitem__',
)
KEYERROR_LINE = "KeyError: 'PAYMENT_API_URL'"
STARTUP_FAILED_LINE = "ERROR:    Application startup failed. Exiting."
# Écrite une fois par pod, juste après le premier crash : l'application journalise
# sa configuration... jeton compris. Sert à montrer le masquage des secrets.
CONFIG_DUMP_LINE = (
    "ERROR:    app.config: configuration lue au moment de l'échec : APP_ENV=prod, "
    f"PAYMENT_PROVIDER=nextpay, PAYMENT_API_TOKEN={FAKE_TOKEN}, PAYMENT_API_URL=<absente>"
)

# Log du job « test » en échec (scénario ci_failure), avec les codes couleur et
# marqueurs de section d'un vrai runner GitLab (le backend les nettoie).
CI_TRACE = "\n".join((  # noqa: FLY002 (une ligne de log par élément)
    "\x1b[0KRunning with gitlab-runner 17.5.2 (c6eae8d7)\x1b[0;m",
    "\x1b[0K  on lab-runner-1 Lb7xQ2pZ, system ID: s_4f0c2a9e7b1d\x1b[0;m",
    "section_start:1731852000:prepare_executor\r\x1b[0K\x1b[0K\x1b[36;1mPreparing the \"docker\" executor\x1b[0;m",
    "\x1b[0KUsing Docker executor with image python:3.11-slim ...\x1b[0;m",
    "section_end:1731852004:prepare_executor\r\x1b[0K",
    "section_start:1731852004:get_sources\r\x1b[0K\x1b[0K\x1b[36;1mGetting source from Git repository\x1b[0;m",
    "\x1b[32;1mFetching changes with git depth set to 20...\x1b[0;m",
    "Checking out 5d4c3b2a as detached HEAD (ref is main)...",
    "section_end:1731852007:get_sources\r\x1b[0K",
    "section_start:1731852007:step_script\r\x1b[0K\x1b[0K\x1b[36;1mExecuting \"step_script\" stage of the job script\x1b[0;m",
    "\x1b[32;1m$ pip install -q -r requirements.txt -r requirements-dev.txt\x1b[0;m",
    "\x1b[32;1m$ pytest -q\x1b[0;m",
    "........................................F.                               [100%]",
    "=================================== FAILURES ===================================",
    "____________________________ test_apply_promo_code _____________________________",
    "",
    "    def test_apply_promo_code():",
    '        cart = Cart(items=[Item(sku="TSHIRT-01", price=Decimal("50.00"), qty=2)])',
    '        cart.apply_promo("AUTOMNE15")',
    '>       assert cart.total == Decimal("85.00")',
    "E       AssertionError: assert Decimal('90.00') == Decimal('85.00')",
    "E        +  where Decimal('90.00') = <app.cart.Cart object at 0x7f3c2a1b9d50>.total",
    "",
    "tests/test_cart.py:42: AssertionError",
    "=========================== short test summary info ============================",
    "FAILED tests/test_cart.py::test_apply_promo_code - AssertionError: assert Decimal('90.00') == Decimal('85.00')",
    "\x1b[31;1m1 failed, 41 passed in 3.87s\x1b[0;m",
    "section_end:1731852031:step_script\r\x1b[0K",
    "section_start:1731852031:cleanup_file_variables\r\x1b[0K\x1b[0K\x1b[36;1mCleaning up project directory and file based variables\x1b[0;m",
    "section_end:1731852032:cleanup_file_variables\r\x1b[0K",
    "\x1b[31;1mERROR: Job failed: exit code 1\x1b[0;m",
    "",
))
OK_TRACE = "\x1b[32;1m$ make ci\x1b[0;m\nAll checks passed.\n\x1b[32;1mJob succeeded\x1b[0;m\n"


# ── Petits outils ─────────────────────────────────────────────────────────────


def iso(t: float, millis: bool = False) -> str:
    """Horodatage UTC au format RFC 3339 (secondes, ou millisecondes pour GitLab)."""
    dt = datetime.fromtimestamp(t, tz=timezone.utc)
    if millis:
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def uid(*parts: object) -> str:
    """UID Kubernetes stable, dérivé d'un nom (mêmes objets → mêmes UID)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "doctor-lab/" + "/".join(map(str, parts))))


def hexdigest(*parts: object, size: int = 64) -> str:
    return hashlib.sha256("/".join(map(str, parts)).encode()).hexdigest()[:size]


def fmt_backoff(seconds: int) -> str:
    """Délai au format du kubelet : 40s, 1m20s, 5m0s."""
    return f"{seconds}s" if seconds < 60 else f"{seconds // 60}m{seconds % 60}s"


def log(msg: str) -> None:
    sys.stderr.write(f"doctor-lab: {msg}\n")
    sys.stderr.flush()


def crash_cycles(deploy_at: float, now: float, offset: float) -> list[tuple[float, float]]:
    """Cycles (démarrage, crash) d'un conteneur en CrashLoopBackOff démarrés avant *now*."""
    cycles: list[tuple[float, float]] = []
    start = deploy_at + POD_PULL_S + offset
    i = 0
    while start <= now and len(cycles) < 1000:
        cycles.append((start, start + RUN_S))
        start += RUN_S + (BACKOFFS[i] if i < len(BACKOFFS) else 300)
        i += 1
    return cycles


def next_backoff(n_crashes: int) -> int:
    return BACKOFFS[n_crashes - 1] if 0 < n_crashes <= len(BACKOFFS) else 300


_VALUES_RE = re.compile(r"^apps/[^/]+/([^/]+)/values-(dev|prod)\.yaml$")


def image_tag_from_values(content: str) -> str | None:
    """Lit image.tag d'un values.yaml (sous-ensemble YAML écrit par yaml.dump)."""
    block = re.search(r"^image:[ \t]*\n((?:[ \t]+.*(?:\n|$))+)", content, re.MULTILINE)
    if not block:
        return None
    tag = re.search(r"^[ \t]+tag:[ \t]*['\"]?([^'\"\s#]+)", block.group(1), re.MULTILINE)
    return tag.group(1) if tag else None


def values_file(env: str, tag: str) -> str:
    return (
        f"# Valeurs GitOps de {APP} ({env}) — dépôt simulé par le labo CNP Doctor\n"
        f"replicaCount: {REPLICAS[env]}\n"
        "image:\n"
        f"  repository: {REGISTRY}\n"
        f"  tag: {tag}\n"
        "service:\n"
        "  port: 8000\n"
        "env:\n"
        f"  APP_ENV: {env}\n"
    )


# ── État du labo ──────────────────────────────────────────────────────────────


class Lab:
    """Le scénario et tout ce qui en découle. Les réponses sont calculées à la demande."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.reset(time.time())

    # ── Transitions ───────────────────────────────────────────────────────────

    def reset(self, now: float) -> None:
        """État initial : prod saine sur a1b2c3d4, dev saine sur f4e5d6c7."""
        self.scenario = "healthy"
        self.t0 = now                     # référence des horodatages « il y a N jours »
        self.since = now                  # début de l'état courant
        self.bad_deploy_at: float | None = None
        self.rollback_at: float | None = None
        self.rolled_back_tag: str | None = None
        self.ci_failed_at: float | None = None
        self.gitops_seq = 0
        self.history: dict[str, list[dict]] = {"prod": [], "dev": []}
        self._deploy("prod", SHA_OLD, now - 10 * DAY)
        self._deploy("prod", SHA_GOOD, now - 3 * DAY)
        self._deploy("dev", SHA_GOOD, now - 3 * DAY - 2 * HOUR)
        self._deploy("dev", SHA_BAD, now - 20 * HOUR)
        self.files: dict[str, str] = {
            f"apps/lab-cluster/{APP}/values-prod.yaml": values_file("prod", GOOD),
            f"apps/lab-cluster/{APP}/values-dev.yaml": values_file("dev", BAD),
        }
        self.gitops_commits: list[dict] = []

    def do_break(self, now: float) -> None:
        """Déploie f4e5d6c7 en prod (daté de 3 min) : l'application plante au démarrage."""
        self.reset(now)
        self.scenario = "broken"
        self.bad_deploy_at = now - BREAK_BACKDATE_S
        self._deploy("prod", SHA_BAD, self.bad_deploy_at)
        # Comme le job update-gitops de la CI : le dépôt GitOps porte la nouvelle version.
        self._set_values_tag("prod", BAD, f"ci: deploy {APP} {BAD} to prod", self.bad_deploy_at)

    def do_ci_failure(self, now: float) -> None:
        """Prod saine, mais le dernier pipeline (commit 5d4c3b2a) a échoué au job test."""
        self.reset(now)
        self.scenario = "ci_failure"
        self.ci_failed_at = now

    def on_values_written(self, path: str, content: str, message: str, now: float) -> None:
        """Écriture d'un values-{env}.yaml dans le dépôt GitOps : c'est ici que le
        rollback lancé depuis l'interface fait changer l'état du labo."""
        self.files[path] = content
        self.gitops_commits.append({"at": iso(now), "path": path, "message": message,
                                    "tag": image_tag_from_values(content)})
        m = _VALUES_RE.match(path)
        tag = image_tag_from_values(content)
        if not m or m.group(1) != APP or tag is None:
            log(f"[lab] fichier GitOps {path} écrit (sans effet sur le scénario)")
            return
        env = m.group(2)
        if tag == self.running_tag(env):
            log(f"[lab] {path} : image.tag={tag}, déjà en service, rien ne change")
            return
        if env == "prod" and self.scenario == "broken":
            self.scenario = "rolled_back"
            self.since = self.rollback_at = now
            self.rolled_back_tag = tag
            self._deploy("prod", SHAS.get(tag, tag + "0" * (40 - len(tag))), now)
            log(f"[lab] ROLLBACK : prod revient à {tag} → état rolled_back (application saine)")
            return
        log(f"[lab] {path} : image.tag={tag} écrit, mais le labo ne simule que le rollback "
            f"depuis l'état broken (état inchangé : {self.scenario})")

    def _deploy(self, env: str, sha: str, at: float) -> None:
        """Ajoute une entrée à l'historique ArgoCD de *env*."""
        self.gitops_seq += 1
        entries = self.history[env]
        entries.append({
            "id": (entries[-1]["id"] + 1) if entries else 1,
            "sha": sha,
            "gitops_sha": hashlib.sha1(f"cnp-gitops-{self.gitops_seq}".encode()).hexdigest(),
            "at": at,
        })

    def _set_values_tag(self, env: str, tag: str, message: str, at: float) -> None:
        path = f"apps/lab-cluster/{APP}/values-{env}.yaml"
        self.files[path] = values_file(env, tag)
        self.gitops_commits.append({"at": iso(at), "path": path, "message": message, "tag": tag})

    # ── Lecture de l'état ─────────────────────────────────────────────────────

    def running_tag(self, env: str) -> str:
        if env == "dev":
            return BAD
        if self.scenario == "broken":
            return BAD
        if self.scenario == "rolled_back" and self.rolled_back_tag:
            return self.rolled_back_tag
        return GOOD

    def prod_failing(self) -> bool:
        return self.scenario == "broken"

    def current_deployment(self, env: str) -> dict:
        return self.history[env][-1]

    def summary(self, now: float) -> dict:
        def env_summary(env: str) -> dict:
            pods = self.pods(env, now)
            return {
                "image_tag": self.running_tag(env),
                "argocd_health": self.argocd_app(env, now)["status"]["health"]["status"],
                "pods": [
                    {
                        "name": p["metadata"]["name"],
                        "ready": p["status"]["containerStatuses"][0]["ready"],
                        "restarts": p["status"]["containerStatuses"][0]["restartCount"],
                        "state": next(iter(p["status"]["containerStatuses"][0]["state"])),
                    }
                    for p in pods
                ],
                "history": [
                    {"id": e["id"], "revision": e["sha"][:8], "deployedAt": iso(e["at"])}
                    for e in self.history[env]
                ],
            }

        prod_values = self.files.get(f"apps/lab-cluster/{APP}/values-prod.yaml", "")
        return {
            "scenario": self.scenario,
            "since": iso(self.since),
            "prod": env_summary("prod"),
            "dev": env_summary("dev"),
            "gitops_values_prod_tag": image_tag_from_values(prod_values),
            "gitops_commits": self.gitops_commits[-10:],
            "last_pipeline": {k: v for k, v in self.pipelines(now)[0].items() if k in ("id", "status", "sha")},
            "controls": {
                "POST /lab/break": "déploie f4e5d6c7 en prod : CrashLoopBackOff",
                "POST /lab/ci-failure": "prod saine, dernier pipeline en échec",
                "POST /lab/reset": "retour à l'état initial",
            },
        }

    # ── ArgoCD ────────────────────────────────────────────────────────────────

    def argocd_app(self, env: str, now: float) -> dict:
        tag = self.running_tag(env)
        current = self.current_deployment(env)
        degraded = env == "prod" and self.prod_failing()
        health: dict = {"status": "Degraded" if degraded else "Healthy"}
        if degraded:
            health["message"] = f'Deployment "{APP}" has 0/{REPLICAS[env]} ready replicas'
        return {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "Application",
            "metadata": {
                "name": f"{APP}-{env}", "namespace": "argocd", "uid": uid("argocd", APP, env),
                "creationTimestamp": iso(self.t0 - 30 * DAY),
            },
            "spec": {
                "project": "team-demo",
                "destination": {"server": "https://kubernetes.default.svc", "namespace": env},
                "sources": [
                    {"repoURL": f"{APP_WEB_URL}.git", "targetRevision": "main", "path": "chart"},
                    {"repoURL": f"{GITOPS_WEB_URL}.git", "targetRevision": "main", "ref": "values"},
                ],
                "syncPolicy": {"automated": {"prune": True, "selfHeal": True}},
            },
            "status": {
                "sync": {"status": "Synced", "revisions": [current["sha"], current["gitops_sha"]]},
                "health": health,
                "summary": {"images": [f"{REGISTRY}:{tag}"]},
                "operationState": {
                    "phase": "Succeeded",
                    "message": "successfully synced (all tasks run)",
                    "startedAt": iso(current["at"] - 6),
                    "finishedAt": iso(current["at"]),
                },
                "history": [
                    {
                        "id": e["id"],
                        "revisions": [e["sha"], e["gitops_sha"]],
                        "deployedAt": iso(e["at"]),
                        "deployStartedAt": iso(e["at"] - 6),
                        "initiatedBy": {"automated": True},
                    }
                    for e in self.history[env]
                ],
                "reconciledAt": iso(now),
                "sourceTypes": ["Helm", "Helm"],
            },
        }

    # ── Kubernetes ────────────────────────────────────────────────────────────

    @staticmethod
    def rs_hash(env: str, tag: str) -> str:
        """Hash du ReplicaSet d'une version (le template diffère entre prod et dev)."""
        if env == "prod" and tag in RS_HASH:
            return RS_HASH[tag]
        return hexdigest("rs", env, tag, size=9)

    def _pod_set(self, env: str) -> tuple[str, str, float, list[str]]:
        """(mode, tag, démarrage, noms) des pods actuellement en place dans *env*."""
        if env == "dev":
            start = self.current_deployment("dev")["at"] + 20
            rs = self.rs_hash("dev", BAD)
            return "running", BAD, start, [f"{APP}-{rs}-{s}" for s in POD_SUFFIXES[("dev", "initial")]]
        if self.scenario == "broken":
            names = [f"{APP}-{RS_HASH[BAD]}-{s}" for s in POD_SUFFIXES[("prod", "broken")]]
            return "crashloop", BAD, self.bad_deploy_at or self.t0, names
        if self.scenario == "rolled_back":
            tag = self.rolled_back_tag or GOOD
            names = [f"{APP}-{self.rs_hash('prod', tag)}-{s}" for s in POD_SUFFIXES[("prod", "rolled_back")]]
            return "running", tag, self.rollback_at or self.t0, names
        names = [f"{APP}-{RS_HASH[GOOD]}-{s}" for s in POD_SUFFIXES[("prod", "initial")]]
        return "running", GOOD, self.history["prod"][1]["at"] + 20, names

    def _labels(self, env: str, tag: str) -> dict:
        return {
            "app.kubernetes.io/name": APP,
            "app.kubernetes.io/instance": f"{APP}-{env}",
            "app.kubernetes.io/managed-by": "cnp",
            "pod-template-hash": self.rs_hash(env, tag),
        }

    def pods(self, env: str, now: float) -> list[dict]:
        mode, tag, start, names = self._pod_set(env)
        pods = []
        for i, name in enumerate(names):
            pod_uid = uid("pod", env, name)
            container_id = "containerd://" + hexdigest("container", name)
            base_status = {
                "name": APP,
                "image": f"{REGISTRY}:{tag}",
                "imageID": f"{REGISTRY}@sha256:{hexdigest('image', tag)}",
                "containerID": container_id,
            }
            if mode == "running":
                created = min(start + i, max(start, now))      # jamais dans le futur
                started = min(created + 2, max(created, now))
                status = {**base_status, "ready": True, "started": True, "restartCount": 0,
                          "state": {"running": {"startedAt": iso(started)}}, "lastState": {}}
                phase, ready = "Running", True
            else:
                created = start + POD_STOP_S + i
                cycles = crash_cycles(start, now, offset=2 * i)
                crashes = [c for c in cycles if c[1] <= now]
                status = {**base_status, "ready": False, "started": False, "restartCount": len(crashes)}
                if crashes:
                    last_start, last_crash = crashes[-1]
                    status["lastState"] = {"terminated": {
                        "exitCode": 3, "reason": "Error", "containerID": container_id,
                        "startedAt": iso(last_start), "finishedAt": iso(last_crash),
                    }}
                else:
                    status["lastState"] = {}
                if cycles and cycles[-1][1] > now:
                    # Le conteneur vient de redémarrer et va replanter dans quelques secondes.
                    status["state"] = {"running": {"startedAt": iso(cycles[-1][0])}}
                elif crashes:
                    status["state"] = {"waiting": {
                        "reason": "CrashLoopBackOff",
                        "message": f"back-off {fmt_backoff(next_backoff(len(crashes)))} restarting failed "
                                   f"container={APP} pod={name}_{env}({pod_uid})",
                    }}
                else:
                    status["state"] = {"waiting": {"reason": "ContainerCreating"}}
                phase, ready = "Running", False
            labels = self._labels(env, tag)
            pods.append({
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {
                    "name": name, "namespace": env, "uid": pod_uid, "labels": labels,
                    "creationTimestamp": iso(created), "resourceVersion": str(int(created)),
                    "ownerReferences": [{
                        "apiVersion": "apps/v1", "kind": "ReplicaSet", "name": f"{APP}-{labels['pod-template-hash']}",
                        "uid": uid("rs", env, labels["pod-template-hash"]), "controller": True,
                        "blockOwnerDeletion": True,
                    }],
                },
                "spec": {
                    "containers": [{
                        "name": APP, "image": f"{REGISTRY}:{tag}",
                        "ports": [{"containerPort": 8000, "protocol": "TCP"}],
                        "envFrom": [{"secretRef": {"name": f"{APP}-env", "optional": True}}],
                    }],
                    "nodeName": "lab-node-1", "restartPolicy": "Always",
                },
                "status": {
                    "phase": phase,
                    "conditions": [
                        {"type": "PodScheduled", "status": "True", "lastTransitionTime": iso(created)},
                        {"type": "Ready", "status": "True" if ready else "False",
                         "lastTransitionTime": iso(created + 2)},
                    ],
                    "hostIP": "10.0.0.11",
                    "podIP": f"10.42.{1 if env == 'prod' else 2}.{20 + i}",
                    "startTime": iso(created),
                    "containerStatuses": [status],
                    "qosClass": "Burstable",
                },
            })
        return pods

    def deployment(self, env: str, now: float) -> dict:
        _mode, tag, start, _names = self._pod_set(env)
        pods = self.pods(env, now)
        ready = sum(1 for p in pods if p["status"]["containerStatuses"][0]["ready"])
        desired = REPLICAS[env]
        labels = self._labels(env, tag)
        selector = {k: labels[k] for k in ("app.kubernetes.io/name", "app.kubernetes.io/instance")}
        revision = len(self.history[env])
        status: dict = {
            "observedGeneration": revision, "replicas": desired, "updatedReplicas": desired,
            "conditions": [
                {"type": "Available", "status": "True" if ready >= desired else "False",
                 "reason": "MinimumReplicasAvailable" if ready >= desired else "MinimumReplicasUnavailable",
                 "lastUpdateTime": iso(start), "lastTransitionTime": iso(start)},
                {"type": "Progressing", "status": "True",
                 "reason": "NewReplicaSetAvailable" if ready >= desired else "ReplicaSetUpdated",
                 "lastUpdateTime": iso(start), "lastTransitionTime": iso(start)},
            ],
        }
        if ready:
            status["readyReplicas"] = ready
            status["availableReplicas"] = ready
        if desired - ready:
            status["unavailableReplicas"] = desired - ready
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": APP, "namespace": env, "uid": uid("deploy", env, APP), "generation": revision,
                "labels": {k: v for k, v in labels.items() if k != "pod-template-hash"},
                "annotations": {"deployment.kubernetes.io/revision": str(revision)},
                "creationTimestamp": iso(self.t0 - 30 * DAY), "resourceVersion": str(int(start)),
            },
            "spec": {
                "replicas": desired,
                "selector": {"matchLabels": selector},
                "template": {
                    "metadata": {"labels": {k: v for k, v in labels.items() if k != "pod-template-hash"}},
                    "spec": {"containers": [{
                        "name": APP, "image": f"{REGISTRY}:{tag}",
                        "ports": [{"containerPort": 8000, "protocol": "TCP"}],
                    }]},
                },
                "strategy": {"type": "RollingUpdate",
                             "rollingUpdate": {"maxUnavailable": "25%", "maxSurge": "25%"}},
            },
            "status": status,
        }

    def events(self, env: str, now: float) -> list[dict]:
        """Événements du namespace : BackOff (Warning) des pods en crash, plus quelques Normal."""
        mode, _tag, start, names = self._pod_set(env)
        out: list[dict] = []
        if mode != "crashloop":
            return out
        for i, name in enumerate(names):
            pod_uid = uid("pod", env, name)
            cycles = crash_cycles(start, now, offset=2 * i)
            crashes = [c for c in cycles if c[1] + 5 <= now]
            involved = {"apiVersion": "v1", "kind": "Pod", "name": name, "namespace": env,
                        "uid": pod_uid, "fieldPath": f"spec.containers{{{APP}}}"}
            if cycles:
                out.append(self._event(env, name, involved, "Normal", "Started",
                                       f"Started container {APP}", cycles[0][0], cycles[-1][0], len(cycles)))
            if crashes:
                out.append(self._event(
                    env, name, involved, "Warning", "BackOff",
                    f"Back-off restarting failed container {APP} in pod {name}_{env}({pod_uid})",
                    crashes[0][1] + 5, crashes[-1][1] + 5, 2 * len(crashes) - 1,
                ))
        return out

    def _event(self, env: str, pod: str, involved: dict, typ: str, reason: str, message: str,
               first: float, last: float, count: int) -> dict:
        return {
            "apiVersion": "v1",
            "kind": "Event",
            "metadata": {
                "name": f"{pod}.{hexdigest('event', pod, reason, size=16)}", "namespace": env,
                "uid": uid("event", pod, reason), "creationTimestamp": iso(first),
                "resourceVersion": str(int(last)),
            },
            "involvedObject": involved,
            "reason": reason,
            "message": message,
            "source": {"component": "kubelet", "host": "lab-node-1"},
            "firstTimestamp": iso(first),
            "lastTimestamp": iso(last),
            "count": count,
            "type": typ,
            "eventTime": None,
            "reportingComponent": "kubelet",
            "reportingInstance": "lab-node-1",
        }

    # ── Loki ──────────────────────────────────────────────────────────────────

    def log_entries(self, env: str, qs: float, qe: float, now: float) -> list[tuple[float, dict, str]]:
        """Lignes de logs (horodatage, labels du flux, texte) de *env* entre qs et qe."""
        out: list[tuple[float, dict, str]] = []
        end = min(qe, now)
        if env == "dev":
            _mode, _tag, _start, names = self._pod_set("dev")
            self._serve(out, env, names, qs, end)
            return out
        initial = [f"{APP}-{RS_HASH[GOOD]}-{s}" for s in POD_SUFFIXES[("prod", "initial")]]
        if self.scenario in ("healthy", "ci_failure"):
            self._serve(out, env, initial, qs, end)
            return out
        stop = (self.bad_deploy_at or now) + POD_STOP_S
        self._serve(out, env, initial, qs, min(end, stop))
        self._block(out, env, initial, stop, SHUTDOWN_LINES)
        _mode, _tag, start, names = self._pod_set("prod")
        if self.scenario == "broken":
            self._crash_logs(out, env, names, start, now)
        else:
            # rolled_back : seuls les nouveaux pods sont lus. Choix du labo pour que le
            # rediagnostic soit « healthy » : dans un vrai Loki, les erreurs des pods
            # cassés resteraient dans la fenêtre d'une heure.
            self._block(out, env, names, start + 2, STARTUP_LINES)
            self._serve(out, env, names, start + 3, end)
        return [e for e in out if qs <= e[0] <= qe]

    @staticmethod
    def _stream(env: str, pod: str, stream: str, level: str | None) -> dict:
        labels = {"namespace": env, "container": APP, "app": APP, "pod": pod, "stream": stream}
        if level:
            labels["level"] = level
        return labels

    def _serve(self, out: list, env: str, pods: list[str], lo: float, hi: float, slot: int = 20) -> None:
        """Trafic normal : une ligne d'accès toutes les ~20 s, réparties sur les pods."""
        if hi < lo or not pods:
            return
        for k in range(int(lo // slot), int(hi // slot) + 1):
            ts = k * slot + (k * 7) % 11 + 0.137
            if lo <= ts <= hi:
                out.append((ts, self._stream(env, pods[k % len(pods)], "stdout", "info"),
                            ACCESS_LINES[k % len(ACCESS_LINES)]))

    def _block(self, out: list, env: str, pods: list[str], at: float, lines: tuple[str, ...]) -> None:
        for i, pod in enumerate(pods):
            for j, line in enumerate(lines):
                out.append((at + i + j * 0.01, self._stream(env, pod, "stdout", "info"), line))

    def _crash_logs(self, out: list, env: str, pods: list[str], deploy_at: float, now: float) -> None:
        """Chaque démarrage des pods f4e5d6c7 : trace Python puis arrêt d'uvicorn."""
        for i, pod in enumerate(pods):
            for n, (start, crash) in enumerate(crash_cycles(deploy_at, now, offset=2 * i)):
                out.append((start + 0.10, self._stream(env, pod, "stdout", "info"), STARTUP_LINES[0]))
                out.append((start + 0.12, self._stream(env, pod, "stdout", "info"), STARTUP_LINES[1]))
                if crash > now:
                    continue          # ce démarrage n'a pas encore planté
                for j, line in enumerate(TRACEBACK_LINES):
                    out.append((crash - 0.05 + j * 0.001, self._stream(env, pod, "stderr", None), line))
                out.append((crash - 0.02, self._stream(env, pod, "stderr", "error"), KEYERROR_LINE))
                out.append((crash, self._stream(env, pod, "stderr", "error"), STARTUP_FAILED_LINE))
                if n == 0:
                    out.append((crash + 0.02, self._stream(env, pod, "stderr", "error"), CONFIG_DUMP_LINE))

    # ── GitLab ────────────────────────────────────────────────────────────────

    def commit_json(self, sha: str) -> dict:
        title, author, ago, _files = COMMITS[sha]
        ref = self.ci_failed_at if sha == SHA_CI and self.ci_failed_at else self.t0
        at = iso(ref - ago, millis=True)
        idx = CHAIN.index(sha)
        return {
            "id": sha, "short_id": sha[:8], "title": title, "message": title + "\n",
            "author_name": author,
            "author_email": author.lower().replace(" ", ".").replace("è", "e") + "@team-demo.lab.local",
            "authored_date": at, "committer_name": author, "committed_date": at, "created_at": at,
            "parent_ids": [CHAIN[idx - 1]] if idx else [],
            "web_url": f"{APP_WEB_URL}/-/commit/{sha}",
        }

    def compare(self, from_ref: str, to_ref: str) -> dict:
        """Commits et fichiers entre deux révisions de la chaîne simulée."""
        def index(ref: str) -> int | None:
            return next((i for i, sha in enumerate(CHAIN) if sha.startswith(ref[:8])), None)

        i, j = index(from_ref), index(to_ref)
        shas = list(CHAIN[i + 1:j + 1]) if i is not None and j is not None and j > i else []
        files: dict[str, str] = {}
        for sha in shas:
            for path, change in COMMITS[sha][3]:
                files.setdefault(path, change)
        diffs = [
            {"old_path": path, "new_path": path, "a_mode": "0" if change == "added" else "100644",
             "b_mode": "100644", "new_file": change == "added", "renamed_file": False,
             "deleted_file": False, "diff": ""}
            for path, change in files.items()
        ]
        commits = [self.commit_json(sha) for sha in shas]
        return {
            "commit": commits[-1] if commits else None,
            "commits": commits,
            "diffs": diffs,
            "compare_timeout": False,
            "compare_same_ref": from_ref == to_ref,
            "web_url": f"{APP_WEB_URL}/-/compare/{from_ref[:8]}...{to_ref[:8]}",
        }

    def pipelines(self, now: float) -> list[dict]:
        """Pipelines du projet de l'application, du plus récent au plus ancien."""
        rows = [
            (1176, SHA_OLD, "success", self.t0 - 10 * DAY - 50 * MIN),
            (1180, SHA_GOOD, "success", self.t0 - 3 * DAY - 50 * MIN),
            (1191, SHA_BAD, "success", self.t0 - 21 * HOUR + 2 * MIN),
        ]
        if self.scenario == "ci_failure" and self.ci_failed_at:
            rows.append((1204, SHA_CI, "failed", self.ci_failed_at - 8 * MIN))
        out = []
        for pid, sha, status, created in reversed(rows):
            out.append({
                "id": pid, "iid": pid - 1000, "project_id": APP_PROJECT_ID, "sha": sha, "ref": "main",
                "status": status, "source": "push", "created_at": iso(created, millis=True),
                "updated_at": iso(created + 4 * MIN, millis=True),
                "web_url": f"{APP_WEB_URL}/-/pipelines/{pid}",
            })
        return out

    def jobs(self, pipeline: dict) -> list[dict]:
        pid = pipeline["id"]
        failed = pipeline["status"] == "failed"
        created = datetime.fromisoformat(pipeline["created_at"].replace("Z", "+00:00")).timestamp()
        spec = [("lint", "test", "success"), ("test", "test", "failed" if failed else "success"),
                ("build", "build", "skipped" if failed else "success"),
                ("update-gitops", "deploy", "skipped" if failed else "success")]
        out = []
        for k, (name, stage, status) in enumerate(spec, 1):
            job = {
                "id": pid * 100 + k, "name": name, "stage": stage, "status": status, "ref": "main",
                "created_at": iso(created, millis=True),
                "started_at": iso(created + 20 * k, millis=True) if status != "skipped" else None,
                "finished_at": iso(created + 20 * k + 35, millis=True) if status != "skipped" else None,
                "duration": 35.2 if status != "skipped" else None,
                "allow_failure": False,
                "web_url": f"{APP_WEB_URL}/-/jobs/{pid * 100 + k}",
                "pipeline": {"id": pid, "project_id": APP_PROJECT_ID, "ref": "main",
                             "sha": pipeline["sha"], "status": pipeline["status"]},
                "user": {"id": 7, "username": "lucas.bernard", "name": "Lucas Bernard"},
            }
            if status == "failed":
                job["failure_reason"] = "script_failure"
            out.append(job)
        return out

    def find_job(self, job_id: int, now: float) -> tuple[dict, dict] | None:
        for pipe in self.pipelines(now):
            for job in self.jobs(pipe):
                if job["id"] == job_id:
                    return pipe, job
        return None


LAB = Lab()


# ── Faux fournisseur IA ───────────────────────────────────────────────────────

_EVIDENCE_RE = re.compile(r"^\[(E\d+)\] \(([a-z_]+)\) (.*)$", re.MULTILINE)
_ACTION_RE = re.compile(r"^\[(A\d+)\] \(([a-z_]+)\) (.*?) — (.*)$", re.MULTILINE)


def _find(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.MULTILINE)
    return m.group(1).strip() if m else None


def _pick_evidence(evidence: list[tuple[str, str, str]], preferred: list[str], first: str | None) -> list[str]:
    """Jusqu'à 5 preuves : *first* d'abord, puis une par source préférée, à tour de rôle."""
    picked: list[str] = []
    if first:
        hit = next((eid for eid, _src, label in evidence if first in label), None)
        if hit:
            picked.append(hit)
    queues = {src: [eid for eid, s, _l in evidence if s == src] for src in preferred}
    while len(picked) < 5 and any(queues.values()):
        for src in preferred:
            while queues[src] and queues[src][0] in picked:
                queues[src].pop(0)
            if queues[src] and len(picked) < 5:
                picked.append(queues[src].pop(0))
    return picked or [eid for eid, _s, _l in evidence[:3]]


def doctor_answer(prompt: str) -> dict:
    """Réponse JSON de « CNP Doctor » construite à partir du dossier envoyé par le backend.

    Ne cite que des identifiants présents dans le prompt et ne nomme que des
    fichiers ou variables qui y figurent, comme on l'exige d'un vrai modèle.
    """
    evidence = _EVIDENCE_RE.findall(prompt)
    actions = _ACTION_RE.findall(prompt)
    app = _find(r"^Application : (.+?) \(environnement", prompt) or "L'application"
    env = _find(r"\(environnement (\w+)\)", prompt) or "prod"
    verdict = _find(r"^Verdict de la plateforme : (\w+)", prompt) or ""
    verdict_label = _find(r"^Verdict de la plateforme : \w+ — (.+)$", prompt) or verdict
    suspect = _find(r"^Déploiement suspect : (\w+),", prompt)
    suspect_when = _find(r"^Déploiement suspect : \w+, (.+)\.$", prompt)
    previous = _find(r"^Version précédente : (\w+),", prompt)
    previous_ran = _find(r"^Version précédente : \w+, en service pendant (.+)\.$", prompt)
    correlation = _find(r"^Force de la corrélation : (\w+)\.", prompt)
    missing_var = "PAYMENT_API_URL" in prompt
    crashloop = "CrashLoopBackOff" in prompt

    if missing_var and verdict in ("regression", "failing", "unstable", ""):
        since = f" depuis le déploiement de {suspect}" if suspect else ""
        headline = f"{app} plante au démarrage en {env}{since} : la variable PAYMENT_API_URL n'est pas définie."
        parts = []
        when = f" ({suspect_when})" if suspect_when else ""
        loop = " et Kubernetes relance les conteneurs en boucle" if crashloop else ""
        parts.append(
            (f"Depuis le déploiement de {suspect}{when}, chaque démarrage" if suspect else "Chaque démarrage")
            + f" s'arrête sur « KeyError: 'PAYMENT_API_URL' »{loop}."
        )
        if previous:
            ran = f" pendant {previous_ran}" if previous_ran else ""
            parts.append(f"La version précédente, {previous}, a tourné sans erreur{ran}.")
        files = [f for f in ("app/config.py", "app/payment/client.py") if f in prompt]
        if files:
            parts.append(
                f"Les changements de cette version touchent {' et '.join(files)} : "
                f"le code lit désormais PAYMENT_API_URL, absente de la configuration de {env}."
            )
        if any(kind == "rollback" for _i, kind, _l, _d in actions) and previous:
            parts.append(f"Revenir à {previous} rétablit le service le temps d'ajouter la variable.")
        version = f"La version {suspect}" if suspect else "La nouvelle version"
        cause = {
            "summary": f"{version} lit la variable PAYMENT_API_URL au démarrage, mais elle n'est pas définie en {env}.",
            "confidence": correlation if correlation in ("haute", "moyenne", "faible") else "moyenne",
            "category": "config",
        }
        cited = _pick_evidence(evidence, ["deployments", "logs", "kubernetes", "git"], "PAYMENT_API_URL")
    elif verdict == "ci_failure" or (re.search(r"pipeline #\d+ : failed", prompt) and not crashloop):
        pipeline = _find(r"Dernier pipeline #(\d+)", prompt)
        job = _find(r"Job « (.+?) » en échec", prompt) or "test"
        # Le backend ne transmet que le début de la fin du log : la ligne « FAILED … »
        # peut manquer, on se rabat alors sur l'en-tête pytest et la ligne « E   … ».
        failed_test = (_find(r"FAILED (\S+) - ", prompt)
                       or _find(r"_{3,} (test_\w+) _{3,}", prompt)
                       or _find(r"def (test_\w+)\(", prompt))
        assertion = (_find(r"FAILED \S+ - (.+)$", prompt)
                     or _find(r"^\s*E\s+(AssertionError: .+)$", prompt))
        headline = (f"{app} tourne normalement en {env}, mais le pipeline"
                    f"{' #' + pipeline if pipeline else ''} a échoué : la nouvelle version n'est pas déployée.")
        detail = f" : {failed_test} ({assertion})" if failed_test and assertion else ""
        explanation = (
            f"Le job « {job} » du dernier pipeline échoue{detail}. Tant que ce job échoue, la nouvelle "
            f"version n'est ni construite ni déployée ; la version en service n'est pas touchée."
        )
        parts = [explanation]
        cause = {
            "summary": (f"Le test {failed_test} échoue sur le dernier commit." if failed_test
                        else f"Le job « {job} » échoue sur le dernier commit."),
            "confidence": "haute" if failed_test else "moyenne",
            "category": "ci",
        }
        cited = _pick_evidence(evidence, ["ci", "argocd", "kubernetes"], "en échec")
    else:
        headline = f"{app} en {env} : {verdict_label}."
        parts = [(
            "Les preuves collectées par la plateforme sont listées ci-dessous. Le fournisseur IA "
            "simulé du labo ne commente en détail que les scénarios du labo."
        )]
        cause = {
            "summary": "La cause n'a pas pu être établie par le fournisseur IA simulé.",
            "confidence": correlation if verdict == "regression" and correlation else "faible",
            "category": "deployment" if verdict == "regression" else "unknown",
        }
        cited = _pick_evidence(evidence, ["deployments", "logs", "kubernetes", "git"], None)

    notes = []
    for aid, kind, label, _desc in actions:
        target = _find(r"version (\w+)", label)
        why = {
            "rollback": (f"Remet en service {target}, qui tournait sans erreur, le temps d'ajouter "
                         f"PAYMENT_API_URL à la configuration de {env}." if missing_var
                         else f"Remet en service {target}, la dernière version saine."),
            "open_repo_compare": ("La comparaison montre le commit qui introduit la lecture de PAYMENT_API_URL."
                                  if missing_var else "Montre ce qui a changé entre les deux versions."),
            "view_logs": "La trace complète de l'erreur au démarrage est dans les logs.",
            "view_history": "L'historique confirme quelle version tournait avant la panne.",
            "open_pipeline": "Le log du job en échec indique le test à corriger.",
            "retry_later": "Les signaux seront plus complets dans une minute.",
            "resume": "Relance l'environnement arrêté.",
            "contact_maintainer": "Le problème se situe côté plateforme, pas dans l'application.",
        }.get(kind, "Action proposée par la plateforme.")
        notes.append({"id": aid, "why": why})

    return {
        "headline": headline[:160],
        "explanation": " ".join(parts),
        "cause": cause,
        "evidence_ids": cited,
        "actions": notes,
    }


CANNED_CHAT = (
    "Je suis le fournisseur IA simulé du labo CNP Doctor : je sais seulement rédiger les "
    "diagnostics du scénario de démo. Pour discuter avec un vrai modèle, relance le labo "
    "avec ./scripts/doctor-lab/start.sh --real-ai."
)


def chat_completion(body: dict) -> dict:
    messages = body.get("messages") or []
    system = "\n".join(str(m.get("content") or "") for m in messages if m.get("role") == "system")
    user = next((str(m.get("content") or "") for m in reversed(messages) if m.get("role") == "user"), "")
    if "CNP Doctor" in system:
        content = json.dumps(doctor_answer(user), ensure_ascii=False)
    else:
        content = CANNED_CHAT
    prompt_chars = sum(len(str(m.get("content") or "")) for m in messages)
    usage = {"prompt_tokens": max(1, prompt_chars // 4), "completion_tokens": max(1, len(content) // 4)}
    usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    return {
        "id": "chatcmpl-lab-" + hexdigest("chat", time.time(), size=12),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.get("model") or "lab-doctor",
        "system_fingerprint": "doctor-lab",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                     "finish_reason": "stop"}],
        "usage": usage,
    }


# ── Serveur HTTP ──────────────────────────────────────────────────────────────

_MATCHER_RE = re.compile(r'([\w.]+)\s*(=~|!~|!=|=)\s*"([^"]*)"')


def _k8s_status(code: int, reason: str, message: str, details: dict | None = None) -> dict:
    body = {"kind": "Status", "apiVersion": "v1", "metadata": {}, "status": "Failure",
            "message": message, "reason": reason, "code": code}
    if details:
        body["details"] = details
    return body


def _selector(raw: str) -> list[tuple[str, str, str]]:
    """labelSelector / fieldSelector simples : a=b,c!=d."""
    out = []
    for part in filter(None, (p.strip() for p in raw.split(","))):
        m = re.match(r"^([\w./-]+)\s*(==|!=|=)\s*(.*)$", part)
        if m:
            out.append((m.group(1), "!=" if m.group(2) == "!=" else "=", m.group(3)))
    return out


def _match(value: str, op: str, expected: str) -> bool:
    return value == expected if op == "=" else value != expected


def _field(obj: dict, dotted: str) -> str:
    cur: object = obj
    for key in dotted.split("."):
        cur = cur.get(key) if isinstance(cur, dict) else None
    return "" if cur is None else str(cur)


class Handler(BaseHTTPRequestHandler):
    server_version = "doctor-lab/1.0"
    protocol_version = "HTTP/1.1"

    # ── Plomberie ─────────────────────────────────────────────────────────────

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def log_message(self, fmt: str, *args) -> None:
        log(fmt % args)

    def _read_body(self) -> bytes:
        # Toujours lu en entier : la connexion reste ouverte (HTTP/1.1 keep-alive).
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _json_body(self) -> dict:
        raw = self._raw_body
        if not raw:
            return {}
        try:  # JSON quel que soit le Content-Type annoncé (curl -d envoie du « form »)
            data = json.loads(raw)
        except ValueError:
            return {k: v[0] for k, v in parse_qs(raw.decode("utf-8", "replace")).items()}
        return data if isinstance(data, dict) else {}

    def _send(self, status: int, body: object, content_type: str = "application/json",
              headers: dict | None = None) -> None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, bytes):
            data = body
        else:
            data = str(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _has_token(self) -> bool:
        return bool(self.headers.get("Authorization") or self.headers.get("PRIVATE-TOKEN"))

    def _dispatch(self, method: str) -> None:
        self._raw_body = self._read_body()
        url = urlparse(self.path)
        query = {k: v for k, v in parse_qs(url.query, keep_blank_values=True).items()}
        # Segments décodés un par un : GitLab encode les chemins (team-demo%2Fdemo-shop).
        segments = [unquote(s) for s in url.path.split("/") if s]
        now = time.time()
        try:
            with LAB.lock:
                if not segments or segments[0] in ("healthz", "ready"):
                    return self._send(200, "ok", "text/plain")
                head, rest = segments[0], segments[1:]
                if head == "lab":
                    return self._lab(method, rest, now)
                if head == "loki":
                    return self._loki(rest, query, now)
                if head == "argocd":
                    return self._argocd(method, rest, now)
                if head == "k8s":
                    return self._k8s(method, rest, query, now)
                if head == "gitlab":
                    return self._gitlab(method, rest, query, now)
                if head == "llm":
                    return self._llm(method, rest)
                if head == "prometheus":
                    return self._prometheus(rest)
                if head == "lab-gitlab":
                    return self._gitlab_page(rest, now)
            self._send(404, {"error": "not found", "path": url.path})
        except Exception as exc:  # noqa: BLE001 (le labo ne doit jamais tomber pendant une démo)
            log(f"ERREUR {method} {self.path}: {type(exc).__name__}: {exc}")
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    # ── /lab ─────────────────────────────────────────────────────────────────

    def _lab(self, method: str, rest: list[str], now: float) -> None:
        action = rest[0] if rest else "state"
        if method == "GET" and action == "state":
            return self._send(200, LAB.summary(now))
        if method == "POST" and action in ("break", "ci-failure", "reset"):
            if action == "break":
                LAB.do_break(now)
                log(f"[lab] PANNE : {BAD} déployée en prod (datée de {BREAK_BACKDATE_S // 60} min), "
                    "pods en CrashLoopBackOff")
            elif action == "ci-failure":
                LAB.do_ci_failure(now)
                log("[lab] ÉCHEC CI : dernier pipeline #1204 en échec (job test), prod saine")
            else:
                LAB.reset(now)
                log("[lab] REMISE À ZÉRO : prod saine sur a1b2c3d4")
            return self._send(200, LAB.summary(now))
        self._send(404, {"error": "use GET /lab/state or POST /lab/break | /lab/ci-failure | /lab/reset"})

    # ── Loki ─────────────────────────────────────────────────────────────────

    def _loki(self, rest: list[str], query: dict, now: float) -> None:
        if rest[:3] != ["api", "v1", "query_range"]:
            if rest[-1:] == ["ready"]:
                return self._send(200, "ready", "text/plain")
            return self._send(404, {"status": "error", "error": "unsupported Loki endpoint"})
        matchers = _MATCHER_RE.findall((query.get("query") or [""])[0])
        end = int((query.get("end") or [0])[0] or 0) / 1e9 or now
        start = int((query.get("start") or [0])[0] or 0) / 1e9 or end - HOUR
        limit = int((query.get("limit") or [100])[0] or 100)
        backward = (query.get("direction") or ["backward"])[0] != "forward"

        entries = []
        for env in NAMESPACES:
            for ts, labels, line in LAB.log_entries(env, start, end, now):
                if all(self._label_ok(labels.get(k, ""), op, v) for k, op, v in matchers):
                    entries.append((ts, labels, line))
        entries.sort(key=lambda e: e[0], reverse=backward)
        entries = entries[:limit]

        streams: dict[tuple, dict] = {}
        for ts, labels, line in entries:
            key = tuple(sorted(labels.items()))
            streams.setdefault(key, {"stream": labels, "values": []})["values"].append(
                [str(int(ts * 1e9)), line])
        self._send(200, {"status": "success", "data": {
            "resultType": "streams", "result": list(streams.values()),
            "stats": {"summary": {"totalEntriesReturned": len(entries)}},
        }})

    @staticmethod
    def _label_ok(value: str, op: str, expected: str) -> bool:
        if op == "=":
            return value == expected
        if op == "!=":
            return value != expected
        matched = re.fullmatch(expected, value) is not None
        return matched if op == "=~" else not matched

    # ── ArgoCD ───────────────────────────────────────────────────────────────

    def _argocd(self, method: str, rest: list[str], now: float) -> None:
        if not self._has_token():
            return self._send(401, {"error": "no session information", "code": 16})
        if rest == ["api", "version"]:
            return self._send(200, {"Version": "v2.13.1+lab"})
        if rest[:3] != ["api", "v1", "applications"]:
            return self._send(404, {"error": "unsupported ArgoCD endpoint", "code": 5})
        names = {f"{APP}-{env}": env for env in NAMESPACES}
        if len(rest) == 3 and method == "GET":
            return self._send(200, {"items": [LAB.argocd_app(env, now) for env in NAMESPACES]})
        name = rest[3]
        env = names.get(name)
        if env is None:
            msg = f'applications.argoproj.io "{name}" not found'
            return self._send(404, {"error": msg, "code": 5, "message": msg})
        if len(rest) == 4 and method == "GET":
            return self._send(200, LAB.argocd_app(env, now))
        if rest[4:] == ["sync"] and method == "POST":
            log(f"[lab] sync ArgoCD demandée pour {name} (sans effet)")
            return self._send(200, LAB.argocd_app(env, now))
        self._send(404, {"error": "unsupported ArgoCD endpoint", "code": 5})

    # ── Kubernetes ───────────────────────────────────────────────────────────

    def _k8s(self, method: str, rest: list[str], query: dict, now: float) -> None:
        if not self._has_token():
            return self._send(401, _k8s_status(401, "Unauthorized", "Unauthorized"))
        if method != "GET":
            return self._send(403, _k8s_status(403, "Forbidden", "le cluster du labo est en lecture seule"))
        if rest == ["version"]:
            return self._send(200, {"major": "1", "minor": "30", "gitVersion": "v1.30.4+lab",
                                    "platform": "linux/amd64"})
        rv = {"resourceVersion": str(int(now))}
        label_sel = _selector((query.get("labelSelector") or [""])[0])
        field_sel = _selector((query.get("fieldSelector") or [""])[0])

        if rest[:2] == ["api", "v1"] and rest[2:3] == ["namespaces"]:
            all_ns = ("default", "kube-system", "argocd", "monitoring") + NAMESPACES
            if len(rest) == 3:
                return self._send(200, {"apiVersion": "v1", "kind": "NamespaceList", "metadata": rv,
                                        "items": [self._namespace(n) for n in all_ns]})
            ns = rest[3]
            if len(rest) == 4:
                if ns in all_ns:
                    return self._send(200, self._namespace(ns))
                return self._not_found("namespaces", ns, "")
            kind = rest[4]
            if kind == "pods":
                pods = LAB.pods(ns, now) if ns in NAMESPACES else []
                pods = [p for p in pods
                        if all(_match(p["metadata"]["labels"].get(k, ""), op, v) for k, op, v in label_sel)
                        and all(_match(_field(p, k), op, v) for k, op, v in field_sel)]
                if len(rest) == 5:
                    return self._send(200, {"apiVersion": "v1", "kind": "PodList", "metadata": rv, "items": pods})
                pod = next((p for p in pods if p["metadata"]["name"] == rest[5]), None)
                return self._send(200, pod) if pod else self._not_found("pods", rest[5], "")
            if kind == "events" and len(rest) == 5:
                events = LAB.events(ns, now) if ns in NAMESPACES else []
                events = [e for e in events if all(_match(_field(e, k), op, v) for k, op, v in field_sel)]
                return self._send(200, {"apiVersion": "v1", "kind": "EventList", "metadata": rv, "items": events})

        if rest[:3] == ["apis", "apps", "v1"] and rest[3:4] == ["namespaces"] and rest[5:6] == ["deployments"]:
            ns = rest[4]
            deps = [LAB.deployment(ns, now)] if ns in NAMESPACES else []
            if len(rest) == 6:
                return self._send(200, {"apiVersion": "apps/v1", "kind": "DeploymentList",
                                        "metadata": rv, "items": deps})
            dep = next((d for d in deps if d["metadata"]["name"] == rest[6]), None)
            return self._send(200, dep) if dep else self._not_found("deployments", rest[6], "apps")

        self._send(404, _k8s_status(404, "NotFound", "the server could not find the requested resource"))

    def _not_found(self, kind: str, name: str, group: str) -> None:
        full = f"{kind}.{group}" if group else kind
        self._send(404, _k8s_status(404, "NotFound", f'{full} "{name}" not found',
                                    {"name": name, "group": group, "kind": kind}))

    @staticmethod
    def _namespace(name: str) -> dict:
        return {"apiVersion": "v1", "kind": "Namespace",
                "metadata": {"name": name, "uid": uid("ns", name),
                             "creationTimestamp": iso(LAB.t0 - 60 * DAY),
                             "labels": {"kubernetes.io/metadata.name": name}},
                "spec": {"finalizers": ["kubernetes"]}, "status": {"phase": "Active"}}

    # ── GitLab ───────────────────────────────────────────────────────────────

    def _gitlab(self, method: str, rest: list[str], query: dict, now: float) -> None:
        if rest[:2] != ["api", "v4"]:
            return self._send(404, {"message": "404 Not Found"})
        if not self._has_token():
            return self._send(401, {"message": "401 Unauthorized"})
        rest = rest[2:]
        q = {k: v[0] for k, v in query.items()}
        if rest == ["user"] or rest[:1] == ["users"]:
            return self._send(200, {"id": 1, "username": "cnp-lab-bot", "name": "CNP Lab Bot",
                                    "state": "active", "web_url": f"{PUBLIC_URL}/lab-gitlab/cnp-lab-bot"})
        if rest[:1] != ["projects"] or len(rest) < 2:
            return self._send(404, {"message": "404 Not Found"})
        project = self._project(rest[1])
        if project is None:
            return self._send(404, {"message": "404 Project Not Found"})
        sub = rest[2:]
        if not sub:
            return self._send(200, project)
        pid = project["id"]

        if sub[0] == "pipelines" and method == "GET":
            pipes = LAB.pipelines(now) if pid == APP_PROJECT_ID else []
            if len(sub) == 1:
                per_page = int(q.get("per_page") or 20)
                return self._send(200, pipes[:per_page])
            pipe = next((p for p in pipes if str(p["id"]) == sub[1]), None)
            if pipe is None:
                return self._send(404, {"message": "404 Not found"})
            if len(sub) == 2:
                return self._send(200, pipe)
            if sub[2] == "jobs":
                scope = query.get("scope[]") or query.get("scope") or []
                jobs = [j for j in LAB.jobs(pipe) if not scope or j["status"] in scope]
                return self._send(200, jobs[: int(q.get("per_page") or 20)])

        if sub[0] == "jobs" and len(sub) >= 2 and method == "GET":
            found = LAB.find_job(int(sub[1]), now) if sub[1].isdigit() else None
            if found is None:
                return self._send(404, {"message": "404 Not found"})
            pipe, job = found
            if len(sub) == 2:
                return self._send(200, job)
            if sub[2] == "trace":
                trace = CI_TRACE if job["status"] == "failed" else OK_TRACE
                return self._send(200, trace.encode(), "text/plain")

        if sub[:2] == ["repository", "compare"] and method == "GET":
            return self._send(200, LAB.compare(q.get("from", ""), q.get("to", "")))

        if sub[:2] == ["repository", "tree"] and method == "GET":
            files = LAB.files if pid == GITOPS_PROJECT_ID else {}
            items = [{"id": hexdigest("blob", p, size=40), "name": p.rsplit("/", 1)[-1], "type": "blob",
                      "path": p, "mode": "100644"} for p in sorted(files)]
            return self._send(200, items)

        if sub[:2] == ["repository", "files"] and len(sub) >= 3:
            return self._gitlab_file(method, pid, sub[2], sub[3:], q, now)

        if sub[:2] == ["repository", "commits"] and method == "POST":
            return self._gitlab_commit(pid, self._json_body(), now)

        self._send(404, {"message": "404 Not Found"})

    def _project(self, ref: str) -> dict | None:
        projects = {
            APP_PROJECT_ID: (APP_PROJECT_PATH, "demo-shop", APP_WEB_URL),
            GITOPS_PROJECT_ID: (GITOPS_PROJECT_PATH, "cnp-gitops", GITOPS_WEB_URL),
        }
        for pid, (path, name, web_url) in projects.items():
            if ref in (str(pid), path):
                namespace = path.rsplit("/", 1)[0]
                return {
                    "id": pid, "name": name, "path": name, "path_with_namespace": path,
                    "name_with_namespace": f"{namespace} / {name}", "default_branch": "main",
                    "web_url": web_url, "http_url_to_repo": f"{web_url}.git",
                    "visibility": "private", "last_activity_at": iso(time.time(), millis=True),
                    "namespace": {"id": 990001 if pid == APP_PROJECT_ID else 990100, "path": namespace,
                                  "full_path": namespace, "kind": "group"},
                }
        return None

    def _gitlab_file(self, method: str, pid: int, path: str, tail: list[str], q: dict, now: float) -> None:
        files = LAB.files if pid == GITOPS_PROJECT_ID else {}
        if method == "GET":
            content = files.get(path)
            if content is None:
                return self._send(404, {"message": "404 File Not Found"})
            if tail == ["raw"]:
                return self._send(200, content.encode(), "text/plain; charset=utf-8")
            data = content.encode()
            return self._send(200, {
                "file_name": path.rsplit("/", 1)[-1], "file_path": path, "size": len(data),
                "encoding": "base64", "content": base64.b64encode(data).decode(),
                "content_sha256": hashlib.sha256(data).hexdigest(), "ref": q.get("ref", "main"),
                "blob_id": hashlib.sha1(data).hexdigest(), "commit_id": hexdigest("head", now, size=40),
                "last_commit_id": hexdigest("last", path, size=40), "execute_filemode": False,
            })
        if method in ("PUT", "POST"):
            if pid != GITOPS_PROJECT_ID:
                return self._send(403, {"message": "403 Forbidden : seul le dépôt GitOps est modifiable"})
            body = self._json_body()
            exists = path in files
            if method == "PUT" and not exists:
                return self._send(400, {"message": "A file with this name doesn't exist"})
            if method == "POST" and exists:
                return self._send(400, {"message": "A file with this name already exists"})
            content = str(body.get("content") or "")
            if body.get("encoding") == "base64":
                content = base64.b64decode(content).decode("utf-8", "replace")
            log(f"[lab] GitLab {method} {path} : « {body.get('commit_message', '')} »")
            LAB.on_values_written(path, content, str(body.get("commit_message") or ""), now)
            return self._send(201 if method == "POST" else 200,
                              {"file_path": path, "branch": body.get("branch") or "main"})
        self._send(405, {"message": "405 Method Not Allowed"})

    def _gitlab_commit(self, pid: int, body: dict, now: float) -> None:
        """API Commits (arrêt/relance d'un environnement) : fichiers enregistrés, sans simulation."""
        if pid != GITOPS_PROJECT_ID:
            return self._send(403, {"message": "403 Forbidden : seul le dépôt GitOps est modifiable"})
        message = str(body.get("commit_message") or "")
        for action in body.get("actions") or []:
            path = action.get("file_path") or ""
            if action.get("action") == "delete":
                LAB.files.pop(path, None)
                log(f"[lab] GitLab commit : suppression de {path}")
            else:
                content = str(action.get("content") or "")
                if action.get("encoding") == "base64":
                    content = base64.b64decode(content).decode("utf-8", "replace")
                log(f"[lab] GitLab commit : {action.get('action')} {path} « {message} »")
                LAB.on_values_written(path, content, message, now)
        sha = hexdigest("commit", now, size=40)
        self._send(201, {"id": sha, "short_id": sha[:8], "title": message.splitlines()[0] if message else "",
                         "created_at": iso(now, millis=True), "web_url": f"{GITOPS_WEB_URL}/-/commit/{sha}"})

    # ── Fournisseur IA ───────────────────────────────────────────────────────

    def _llm(self, method: str, rest: list[str]) -> None:
        if not self._has_token():
            return self._send(401, {"error": {"message": "missing API key", "type": "invalid_request_error"}})
        if rest == ["v1", "models"] and method == "GET":
            return self._send(200, {"object": "list", "data": [{"id": "lab-doctor", "object": "model"}]})
        if rest == ["v1", "chat", "completions"] and method == "POST":
            body = self._json_body()
            if not isinstance(body.get("messages"), list):
                return self._send(400, {"error": {"message": "messages is required",
                                                  "type": "invalid_request_error"}})
            answer = chat_completion(body)
            kind = "diagnostic Doctor" if answer["choices"][0]["message"]["content"].startswith("{") else "chat"
            log(f"[lab] IA simulée : réponse {kind} ({answer['usage']['total_tokens']} jetons)")
            return self._send(200, answer)
        self._send(404, {"error": {"message": "unknown endpoint", "type": "invalid_request_error"}})

    # ── Prometheus vide ──────────────────────────────────────────────────────

    def _prometheus(self, rest: list[str]) -> None:
        kind = "matrix" if rest[-1:] == ["query_range"] else "vector"
        self._send(200, {"status": "success", "data": {"resultType": kind, "result": []}})

    # ── Pages « GitLab » pour les liens de la carte ──────────────────────────

    def _gitlab_page(self, rest: list[str], now: float) -> None:
        path = "/".join(rest)
        title, body = "GitLab simulé", f"<p>Page simulée par le labo CNP Doctor : <code>{html.escape(path)}</code></p>"
        if "-" in rest:
            what = rest[rest.index("-") + 1:]
            if what[:1] == ["compare"] and what[1:]:
                a, _, b = what[1].partition("...")
                cmp_ = LAB.compare(a, b)
                title = f"Comparaison {a}...{b}"
                body = "<h2>Commits</h2><ul>" + "".join(
                    f"<li><code>{c['short_id']}</code> {html.escape(c['title'])} — {html.escape(c['author_name'])}</li>"
                    for c in cmp_["commits"]) + "</ul><h2>Fichiers modifiés</h2><ul>" + "".join(
                    f"<li><code>{html.escape(d['new_path'])}</code>{' (nouveau)' if d['new_file'] else ''}</li>"
                    for d in cmp_["diffs"]) + "</ul>"
            elif what[:1] == ["jobs"] and what[1:] and what[1].isdigit():
                found = LAB.find_job(int(what[1]), now)
                if found:
                    job = found[1]
                    trace = CI_TRACE if job["status"] == "failed" else OK_TRACE
                    clean = re.sub(r"section_(?:start|end):\d+:[\w.-]+\r?", "", re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", trace))
                    title = f"Job #{job['id']} « {job['name']} » : {job['status']}"
                    body = f"<pre>{html.escape(clean)}</pre>"
            elif what[:1] == ["pipelines"] and what[1:]:
                pipe = next((p for p in LAB.pipelines(now) if str(p["id"]) == what[1]), None)
                if pipe:
                    title = f"Pipeline #{pipe['id']} : {pipe['status']}"
                    body = "<ul>" + "".join(
                        f"<li><a href=\"{j['web_url']}\">{html.escape(j['name'])}</a> ({j['stage']}) : {j['status']}</li>"
                        for j in LAB.jobs(pipe)) + "</ul>"
            elif what[:1] == ["commit"] and what[1:] and what[1] in COMMITS:
                c = LAB.commit_json(what[1])
                title = f"Commit {c['short_id']}"
                body = f"<p>{html.escape(c['title'])} — {html.escape(c['author_name'])}</p><ul>" + "".join(
                    f"<li><code>{html.escape(p)}</code> ({ch})</li>" for p, ch in COMMITS[what[1]][3]) + "</ul>"
        page = (
            "<!doctype html><html lang=\"fr\"><head><meta charset=\"utf-8\">"
            f"<title>{html.escape(title)}</title><style>body{{font:15px system-ui,sans-serif;max-width:60rem;"
            "margin:2rem auto;padding:0 1rem}pre{background:#f4f4f5;padding:1rem;overflow:auto}"
            ".lab{color:#92400e;background:#fef3c7;padding:.5rem .75rem;border-radius:6px}</style></head><body>"
            "<p class=\"lab\">GitLab simulé : labo CNP Doctor, aucune donnée réelle.</p>"
            f"<h1>{html.escape(title)}</h1>{body}</body></html>"
        )
        self._send(200, page, "text/html; charset=utf-8")


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9000
    bind = os.environ.get("LAB_BIND", "0.0.0.0")
    server = ThreadingHTTPServer((bind, port), Handler)
    server.daemon_threads = True
    log(f"serveur du labo prêt sur {bind}:{port} (liens publics : {PUBLIC_URL}) — état : {LAB.scenario}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
