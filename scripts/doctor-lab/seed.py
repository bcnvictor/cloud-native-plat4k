"""Labo CNP Doctor : données de démo (idempotent, uniquement dans le labo).

À lancer dans le conteneur backend du projet cnp-doctor-lab, depuis la racine du dépôt :

    docker compose -p cnp-doctor-lab -f docker-compose.yml -f scripts/doctor-lab/compose.lab.yml \\
      exec -T backend python - < scripts/doctor-lab/seed.py

    ... exec -T backend python - --clean-events < scripts/doctor-lab/seed.py
        (nettoyage seul : utilisé par break.sh, ci-failure.sh et reset.sh)

Crée ou remet d'aplomb :
  - les comptes admin / maintainer / dev / viewer @cnp.local (mot de passe = préfixe) ;
  - le groupe Team Demo (990001) et ses membres (maintainer 40, developer 30, viewer 20) ;
  - le cluster « lab-cluster », en ligne, dont ArgoCD, Loki et l'API Kubernetes sont le
    serveur simulé doctor-lab ; son kubeconfig et son jeton ArgoCD vont dans le Vault du labo ;
  - l'application demo-shop (projet GitLab 4242), avec l'IA activée.

Nettoie aussi les événements plateforme de demo-shop laissés par une répétition
précédente : un « app.health.degraded » ou un « app.rollback » ancien fausserait la
chronologie du diagnostic suivant (corrélation rétrogradée, déploiement pris pour un rollback).

Refuse de tourner si le backend n'est pas branché sur le Vault du labo : un cluster
d'identifiant N lirait sinon le vrai secret clusters/N du Vault partagé.
"""
import asyncio
import sys
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

LAB_VAULT_ADDR = "http://lab-vault:8200"
LAB_MARKER = "cnp-doctor-lab"          # écrit par le service lab-vault-init
LAB_URL = "http://doctor-lab:9000"     # serveur simulé, vu depuis le réseau Compose
PUBLIC_URL = "http://localhost:9009"   # le même, vu depuis le navigateur
CLUSTER_NAME = "lab-cluster"           # doit rester « lab-cluster » : chemin du values-prod.yaml simulé
APP_SLUG = "demo-shop"
APP_PROJECT_ID = 4242

USERS = [  # (email, mot de passe, rôle plateforme)
    ("admin@cnp.local", "admin", "ADMIN"),
    ("maintainer@cnp.local", "maintainer", "DEV"),
    ("dev@cnp.local", "dev", "DEV"),
    ("viewer@cnp.local", "viewer", "VIEWER"),
]
GROUP = (990001, "Team Demo", "cnp-apps/team-demo")
MEMBERS = [  # (email, niveau GitLab) — 40 maintainer, 30 developer, 20 viewer
    ("maintainer@cnp.local", 40),
    ("dev@cnp.local", 30),
    ("viewer@cnp.local", 20),
]

KUBECONFIG = f"""apiVersion: v1
kind: Config
clusters:
- name: {CLUSTER_NAME}
  cluster:
    server: {LAB_URL}/k8s
contexts:
- name: lab
  context:
    cluster: {CLUSTER_NAME}
    user: lab-bot
current-context: lab
users:
- name: lab-bot
  user:
    token: lab-k8s-token
"""


def guard() -> None:
    """Arrête tout si ce backend n'est pas celui du labo."""
    from backend.core.config import settings
    from backend.vault.client import vault_client

    problems = []
    if settings.VAULT_ADDR.rstrip("/") != LAB_VAULT_ADDR:
        problems.append(f"VAULT_ADDR vaut {settings.VAULT_ADDR!r} au lieu de {LAB_VAULT_ADDR!r}")
    for name in ("GITLAB_BASE_URL", "LOKI_URL"):
        if not str(getattr(settings, name)).startswith(LAB_URL):
            problems.append(f"{name} ne vise pas le serveur simulé {LAB_URL}")
    if not problems:
        try:
            marker = vault_client.get_secret("cnp/platform").get("LAB_MARKER")
        except Exception as exc:  # noqa: BLE001
            marker = None
            problems.append(f"lecture du marqueur du Vault du labo impossible ({type(exc).__name__})")
        if marker != LAB_MARKER and not problems:
            problems.append("le Vault joint ne porte pas le marqueur du labo (secret/cnp/platform)")
    if problems:
        sys.exit("[lab] REFUS : ce backend n'est pas celui du labo CNP Doctor.\n  - " + "\n  - ".join(problems))


async def clean_events(db: AsyncSession, app_id: int) -> int:
    """Efface l'historique plateforme de demo-shop (événements, arrêt d'environnement)."""
    from backend.db.models import Application, AppScaleState, Event
    from shared.models import ApplicationStatus

    result = await db.execute(delete(Event).where(Event.app_id == app_id))
    await db.execute(delete(AppScaleState).where(AppScaleState.app_id == app_id))
    app = await db.get(Application, app_id)
    if app is not None:
        app.last_known_status = ApplicationStatus.DEPLOYED
        app.last_pipeline_status = "success"
    await db.commit()
    return result.rowcount or 0


async def seed(db: AsyncSession) -> dict:
    from backend.core.security import get_password_hash
    from backend.db.models import (
        AIAppSettings,
        AIGlobalSettings,
        Application,
        ClusterConnection,
        GitLabGroup,
        GitLabGroupMember,
        User,
    )
    from backend.vault.client import vault_client
    from shared.models import (
        AIContextMode,
        ApplicationStatus,
        ClusterStatus,
        MemberStatus,
        UserRole,
    )

    # Comptes
    users: dict[str, User] = {}
    for email, password, role in USERS:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            user = User(email=email, hashed_password=get_password_hash(password), role=UserRole[role])
            db.add(user)
        else:  # identifiants et rôles prévisibles d'une démo à l'autre
            user.hashed_password = get_password_hash(password)
            user.role = UserRole[role]
            user.is_active = True
        users[email] = user

    # Groupe et membres (identifiant inconnu de GitLab : le miroir n'y touche pas)
    gid, gname, gpath = GROUP
    if await db.get(GitLabGroup, gid) is None:
        db.add(GitLabGroup(gitlab_group_id=gid, name=gname, full_path=gpath))
    await db.commit()
    for email, level in MEMBERS:
        uid = users[email].id
        member = (await db.execute(select(GitLabGroupMember).where(
            GitLabGroupMember.gitlab_group_id == gid, GitLabGroupMember.cnp_user_id == uid,
        ))).scalar_one_or_none()
        if member is None:
            db.add(GitLabGroupMember(gitlab_group_id=gid, username=email.split("@")[0],
                                     access_level=level, cnp_user_id=uid, status=MemberStatus.ACTIVE))
        else:
            member.access_level = level
            member.status = MemberStatus.ACTIVE

    # Cluster simulé, en ligne
    cluster = (await db.execute(
        select(ClusterConnection).where(ClusterConnection.name == CLUSTER_NAME)
    )).scalar_one_or_none()
    if cluster is None:
        cluster = ClusterConnection(name=CLUSTER_NAME, kubeconfig_secret_ref="pending")
        db.add(cluster)
    cluster.endpoint = f"{LAB_URL}/k8s"
    cluster.provider = "other"
    cluster.argocd_url = f"{LAB_URL}/argocd"
    cluster.loki_url = LAB_URL
    cluster.prometheus_url = f"{LAB_URL}/prometheus"
    cluster.status = ClusterStatus.ONLINE
    cluster.last_seen_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(cluster)
    # Secrets du cluster : Vault du labo uniquement (vérifié par guard()).
    vault_client.put_secret(path=f"clusters/{cluster.id}", secret={"kubeconfig": KUBECONFIG})
    vault_client.put_secret(path=f"argocd/{cluster.id}", secret={"token": "lab-argocd-token"})
    cluster.kubeconfig_secret_ref = f"secret/clusters/{cluster.id}"

    # Application de démo
    app = (await db.execute(select(Application).where(Application.slug == APP_SLUG))).scalar_one_or_none()
    if app is None:
        app = Application(slug=APP_SLUG, name=APP_SLUG, owner="team-demo")
        db.add(app)
    app.name = APP_SLUG
    app.description = "Boutique de démo du labo CNP Doctor (aucune donnée réelle)"
    app.owner = "team-demo"
    app.owning_gitlab_group_id = gid
    app.gitlab_project_id = APP_PROJECT_ID
    app.target_cluster_id = cluster.id
    app.repo_url = f"{PUBLIC_URL}/lab-gitlab/team-demo/demo-shop"
    app.framework = "fastapi"
    app.origin = "scaffold"   # pas « scaffolded » : aucune injection CI ni suppression de dépôt
    app.expose = False
    app.last_known_status = ApplicationStatus.DEPLOYED
    app.last_pipeline_status = "success"
    await db.commit()
    await db.refresh(app)

    # IA activée pour l'application (chat de l'app) ; le Doctor n'exige que l'activation globale.
    ai = await db.get(AIAppSettings, app.id)
    if ai is None:
        db.add(AIAppSettings(app_id=app.id, ai_enabled=True, ai_context_mode=AIContextMode.METADATA_ONLY))
    else:
        ai.ai_enabled = True
    # Une ligne de réglages IA admin restreindrait les applications autorisées et
    # remplacerait le fournisseur du labo : on la retire, l'environnement fait foi.
    removed_global = (await db.execute(delete(AIGlobalSettings))).rowcount or 0
    await db.commit()

    cleaned = await clean_events(db, app.id)
    return {"app_id": app.id, "cluster_id": cluster.id, "events_cleaned": cleaned,
            "ai_global_settings_removed": removed_global}


async def main() -> None:
    from backend.core.config import settings

    guard()
    clean_only = "--clean-events" in sys.argv[1:]
    engine = create_async_engine(settings.async_database_uri)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            if clean_only:
                from backend.db.models import Application
                app = (await db.execute(
                    select(Application).where(Application.slug == APP_SLUG)
                )).scalar_one_or_none()
                if app is None:
                    sys.exit("[lab] demo-shop introuvable : lance d'abord scripts/doctor-lab/start.sh")
                n = await clean_events(db, app.id)
                print(f"[lab] historique plateforme de demo-shop nettoyé ({n} événement(s))")
                return
            info = await seed(db)
    finally:
        await engine.dispose()

    print(f"[lab] données de démo prêtes : demo-shop (id {info['app_id']}) sur le cluster "
          f"{CLUSTER_NAME} (id {info['cluster_id']}), {info['events_cleaned']} événement(s) nettoyé(s)")
    if info["ai_global_settings_removed"]:
        print("[lab] réglages IA admin supprimés : le fournisseur de l'environnement du labo s'applique")
    print("[lab] comptes : admin@cnp.local/admin · maintainer@cnp.local/maintainer · "
          "dev@cnp.local/dev · viewer@cnp.local/viewer")
    print("[lab] interface : http://localhost:8088/  (API : http://localhost:8008/api/v1/docs)")
    print(f"[lab] application : id {info['app_id']} — API du diagnostic : "
          f"POST http://localhost:8008/api/v1/apps/{info['app_id']}/doctor/diagnose")
    print("[lab] état du scénario : http://localhost:9009/lab/state")


if __name__ == "__main__":
    asyncio.run(main())
