"""Fichiers cnp-gitops écrits par le backend pour un env éphémère (ADR-0030 §4 à §7).

Le backend écrit tout : la déclaration et les ressources plateforme à la création,
puis les values et l'Application de l'app quand un pipeline de la branche a construit
l'image (ADR-0014 : ArgoCD ne voit jamais d'Application sans image). La CI d'une
branche n'a aucun droit d'écriture sur cnp-gitops : son .gitlab-ci.yml n'est pas relu.
"""

import copy
import re
from dataclasses import dataclass

import yaml
from shared.models import ephemeral_env_name, sanitize_k8s_label_value

PULL_SECRET_NAME = "gitlab-registry"
PLATFORM_PROJECT = "cnp-platform"
APP_PROJECT = "cnp-ephemeral"
# Values de l'app lues sur la branche, dans cet ordre (comme update-gitops pour dev)
SOURCE_VALUES_FILES = ("chart/values-dev.yaml", "chart/values.yaml")
# "--" n'apparaît jamais dans un slug : l'Application plateforme ne peut pas entrer en
# collision avec l'Application de l'app d'un autre env (branches `x` et `x-platform`).
PLATFORM_SUFFIX = "--platform"
# Même retry que l'Application de l'app (update-gitops-ephemeral) : la synchro peut
# échouer tant qu'un ancien namespace du même nom est en Terminating.
SYNC_RETRY = {"limit": 10, "backoff": {"duration": "10s", "factor": 2, "maxDuration": "5m"}}


@dataclass(frozen=True)
class EphemeralTarget:
    cluster: str
    app_slug: str
    env_slug: str
    branch: str
    owner: str
    gitops_repo_url: str
    registry_vault_key: str
    registry_server: str

    @property
    def name(self) -> str:
        return ephemeral_env_name(self.app_slug, self.env_slug)

    @property
    def root(self) -> str:
        return f"apps/{self.cluster}/{self.app_slug}/ephemeral/{self.env_slug}"

    @property
    def values_path(self) -> str:
        return f"{self.root}/values.yaml"

    @property
    def app_application_path(self) -> str:
        return f"argocd/{self.cluster}/{self.app_slug}/ephemeral/{self.env_slug}.yaml"

    @property
    def platform_app_path(self) -> str:
        return f"argocd/{self.cluster}/{self.app_slug}/ephemeral/{self.env_slug}{PLATFORM_SUFFIX}.yaml"


def _clean_repo_url(url: str) -> str:
    return re.sub(r"https://[^@/]+@", "https://", url)


def _dump(manifest: dict) -> str:
    return yaml.safe_dump(manifest, default_flow_style=False, sort_keys=False)


def _declaration(t: EphemeralTarget) -> dict:
    # Trace lisible de l'env dans le dépôt (branche d'origine), lue par personne
    return {"app": t.app_slug, "slug": t.env_slug, "name": t.name, "branch": t.branch, "namespace": t.name}


def _namespace(t: EphemeralTarget) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": t.name,
            "labels": {
                "app.kubernetes.io/managed-by": "cnp",
                "cnp.io/app": t.app_slug,
                "cnp.io/env": t.env_slug,
                "cnp.io/env-type": "ephemeral",
                "cnp.io/owner": sanitize_k8s_label_value(t.owner),
                # Le chart vient d'une branche non relue (§6) : pas de pod privilégié, ni
                # hostPath, ni hostNetwork, qui donneraient la main sur le nœud.
                "pod-security.kubernetes.io/enforce": "baseline",
            },
        },
    }


def _registry_pull_secret(t: EphemeralTarget) -> dict:
    dockerconfig = (
        '{"auths":{"' + t.registry_server + '":{"username":"{{ .username }}","password":"{{ .password }}",'
        '"auth":"{{ printf "%s:%s" .username .password | b64enc }}"}}}'
    )
    return {
        "apiVersion": "external-secrets.io/v1",
        "kind": "ExternalSecret",
        "metadata": {"name": PULL_SECRET_NAME, "namespace": t.name},
        "spec": {
            "refreshInterval": "1h",
            "secretStoreRef": {"name": "vault-backend", "kind": "ClusterSecretStore"},
            "target": {
                "name": PULL_SECRET_NAME,
                "creationPolicy": "Owner",
                "template": {
                    "type": "kubernetes.io/dockerconfigjson",
                    "data": {".dockerconfigjson": dockerconfig},
                },
            },
            "data": [
                {"secretKey": "username", "remoteRef": {"key": t.registry_vault_key, "property": "username"}},
                {"secretKey": "password", "remoteRef": {"key": t.registry_vault_key, "property": "password"}},
            ],
        },
    }


def _service_account(t: EphemeralTarget) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "ServiceAccount",
        "metadata": {"name": "default", "namespace": t.name},
        "imagePullSecrets": [{"name": PULL_SECRET_NAME}],
    }


def _platform_application(t: EphemeralTarget) -> dict:
    return {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Application",
        "metadata": {
            "name": f"{t.name}{PLATFORM_SUFFIX}",
            "namespace": "argocd",
            "finalizers": ["resources-finalizer.argocd.argoproj.io"],
        },
        "spec": {
            "project": PLATFORM_PROJECT,
            "source": {
                "repoURL": _clean_repo_url(t.gitops_repo_url),
                "targetRevision": "HEAD",
                "path": f"{t.root}/platform",
            },
            "destination": {"server": "https://kubernetes.default.svc", "namespace": t.name},
            # Pas de CreateNamespace : le Namespace est un manifeste géré, supprimé avec l'Application
            "syncPolicy": {"automated": {"prune": True, "selfHeal": True}, "retry": SYNC_RETRY},
        },
    }


def declaration_files(t: EphemeralTarget) -> list[dict]:
    """Fichiers à committer en une fois dans cnp-gitops à la création de l'env."""
    return [
        {"file_path": f"{t.root}/env.yaml", "content": _dump(_declaration(t))},
        {"file_path": f"{t.root}/platform/namespace.yaml", "content": _dump(_namespace(t))},
        {"file_path": f"{t.root}/platform/registry-pull-secret.yaml", "content": _dump(_registry_pull_secret(t))},
        {"file_path": f"{t.root}/platform/serviceaccount.yaml", "content": _dump(_service_account(t))},
        {"file_path": t.platform_app_path, "content": _dump(_platform_application(t))},
    ]


def argocd_app_names(app_slug: str, env_slug: str) -> tuple[str, str]:
    """Noms des deux Applications ArgoCD de l'env : celle de l'app (CI) et la plateforme."""
    name = ephemeral_env_name(app_slug, env_slug)
    return name, f"{name}{PLATFORM_SUFFIX}"


def destroy_paths(cluster: str, app_slug: str, env_slug: str) -> tuple[list[str], list[str]]:
    """(fichiers, dossiers) de l'env dans cnp-gitops : les deux Applications et tout son
    dossier apps/. Supprimer les Applications laisse ArgoCD purger le namespace (finalizer)."""
    argocd_dir = f"argocd/{cluster}/{app_slug}/ephemeral"
    return (
        [f"{argocd_dir}/{env_slug}.yaml", f"{argocd_dir}/{env_slug}{PLATFORM_SUFFIX}.yaml"],
        [f"apps/{cluster}/{app_slug}/ephemeral/{env_slug}"],
    )


def _app_repo_url(repo_url: str) -> str:
    url = _clean_repo_url(repo_url).rstrip("/")
    return url if url.endswith(".git") else f"{url}.git"


def build_values(source_values: dict, t: EphemeralTarget, image_tag: str) -> dict:
    """Values de l'env : celles de dev lues sur la branche, avec le tag de l'image construite."""
    values = copy.deepcopy(source_values) if isinstance(source_values, dict) else {}
    values.setdefault("image", {})["tag"] = image_tag
    # Les values de dev portent le host de dev : jamais d'Ingress tant que l'env
    # n'a pas son propre host (4K-287), sinon il volerait le trafic de dev.
    values.setdefault("ingress", {})["enabled"] = False
    if t.owner:
        values.setdefault("app", {})["owner"] = t.owner
    return values


def _app_application(t: EphemeralTarget, app_repo_url: str, commit_sha: str) -> dict:
    return {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Application",
        "metadata": {
            "name": t.name,
            "namespace": "argocd",
            "finalizers": ["resources-finalizer.argocd.argoproj.io"],
        },
        "spec": {
            "project": APP_PROJECT,
            "sources": [
                {
                    # Chart figé sur le commit dont l'image a été construite : un push
                    # pas encore buildé ne change ni le chart ni l'image déployés.
                    "repoURL": _app_repo_url(app_repo_url),
                    "targetRevision": commit_sha,
                    "path": "chart",
                    "helm": {"valueFiles": [f"$gitops/{t.values_path}"]},
                },
                {"repoURL": _clean_repo_url(t.gitops_repo_url), "targetRevision": "HEAD", "ref": "gitops"},
            ],
            "destination": {"server": "https://kubernetes.default.svc", "namespace": t.name},
            # Le namespace est créé par l'Application plateforme : réessayer tant qu'il manque
            "syncPolicy": {"automated": {"prune": True, "selfHeal": True}, "retry": SYNC_RETRY},
        },
    }


def deployment_files(
    t: EphemeralTarget, source_values: dict, app_repo_url: str, commit_sha: str
) -> list[dict]:
    """Values et Application de l'app pour le commit `commit_sha`, dont l'image est construite.

    Le tag d'image est le sha court (8 caractères) : celui que docker-build pousse
    (CI_COMMIT_SHORT_SHA).
    """
    values = build_values(source_values, t, commit_sha[:8])
    return [
        {"file_path": t.values_path, "content": _dump(values)},
        {"file_path": t.app_application_path, "content": _dump(_app_application(t, app_repo_url, commit_sha))},
    ]
