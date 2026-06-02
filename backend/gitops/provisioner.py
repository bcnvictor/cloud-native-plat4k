import logging
import urllib.parse
from backend.gitlab.client import GitLabClient
from backend.core.config import settings

logger = logging.getLogger(__name__)

def _generate_argocd_application(app_name: str, repo_url: str, env: str) -> str:
    """Generate the ArgoCD Application manifest for a specific environment."""
    return f"""\
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {app_name}-{env}
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  sources:
    # Source 1: The generic Helm chart from the application code repository
    - repoURL: '{repo_url}'
      targetRevision: HEAD
      path: chart
      helm:
        valueFiles:
          - $gitops/apps/{app_name}/values-{env}.yaml
    # Source 2: The environment surcharges from the GitOps repository
    - repoURL: '{settings.GITOPS_REPO_URL}'
      targetRevision: HEAD
      ref: gitops
  destination:
    server: 'https://kubernetes.default.svc'
    namespace: {env}
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
"""

def _generate_helm_values(app_name: str, repo_url: str, env: str) -> str:
    """Generate the Helm values file for a specific environment."""
    # Extract just the repository path without .git
    image_repository = repo_url.replace("https://gitlab.com/", "registry.gitlab.com/").replace(".git", "")
    
    if env == "staging":
        return f"""\
# {app_name} Staging Surcharges
# Ce fichier est mis à jour automatiquement par le pipeline GitLab CI
# lors de chaque push sur la branche main de l'application.
replicaCount: 1

image:
  repository: {image_repository}
  tag: latest # Mis à jour automatiquement par la CI
  pullPolicy: Always

resources:
  limits:
    cpu: 200m
    memory: 256Mi
  requests:
    cpu: 50m
    memory: 64Mi

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: {app_name}-staging.cri.epita.fr
      paths:
        - path: /
          pathType: ImplementationSpecific
"""
    else:  # prod
        return f"""\
# {app_name} Prod Surcharges
replicaCount: 3

image:
  repository: {image_repository}
  tag: stable # Mis à jour lors des promotions (git tag)
  pullPolicy: IfNotPresent

resources:
  limits:
    cpu: 1000m
    memory: 1Gi
  requests:
    cpu: 250m
    memory: 256Mi

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: {app_name}.cri.epita.fr
      paths:
        - path: /
          pathType: ImplementationSpecific
"""

def provision_gitops(app_name: str, repo_url: str, client: GitLabClient) -> None:
    """
    Provision the GitOps repository with ArgoCD manifests and Helm values for the app.
    Commits 4 files to the GitOps repository in a single commit.
    """
    gitops_project_path = urllib.parse.urlparse(settings.GITOPS_REPO_URL).path.lstrip("/").replace(".git", "")
    
    actions = []
    
    # "upsert" creates the file if absent, overwrites if present — one atomic commit either
    # way. This makes provisioning idempotent: safe to retry or re-onboard without errors.
    for file_path, content in [
        (f"argocd/{app_name}/staging.yaml",      _generate_argocd_application(app_name, repo_url, "staging")),
        (f"argocd/{app_name}/prod.yaml",          _generate_argocd_application(app_name, repo_url, "prod")),
        (f"apps/{app_name}/values-staging.yaml",  _generate_helm_values(app_name, repo_url, "staging")),
        (f"apps/{app_name}/values-prod.yaml",     _generate_helm_values(app_name, repo_url, "prod")),
    ]:
        actions.append({"action": "upsert", "file_path": file_path, "content": content})
    
    logger.info("Provisioning GitOps repository for %s in %s", app_name, gitops_project_path)
    client.push_multiple_files(
        project_path=gitops_project_path,
        branch="main",
        commit_message=f"feat(gitops): provision {app_name} application",
        actions=actions
    )
    logger.info("GitOps repository provisioned for %s", app_name)
