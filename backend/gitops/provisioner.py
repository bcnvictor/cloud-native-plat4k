import logging
import urllib.parse
from backend.gitlab.client import GitLabClient
from backend.core.config import settings

logger = logging.getLogger(__name__)

def _generate_argocd_application(app_name: str, repo_url: str, env: str) -> str:
    """Generate the ArgoCD Application manifest for a specific environment."""
    repo_url_git = repo_url if repo_url.endswith(".git") else repo_url + ".git"
    gitops_url_git = settings.GITOPS_REPO_URL if settings.GITOPS_REPO_URL.endswith(".git") else settings.GITOPS_REPO_URL + ".git"
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
    - repoURL: '{repo_url_git}'
      targetRevision: HEAD
      path: chart
      helm:
        valueFiles:
          - $gitops/apps/{app_name}/values-{env}.yaml
    # Source 2: The environment surcharges from the GitOps repository
    - repoURL: '{gitops_url_git}'
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
    image_repository = repo_url.removesuffix(".git").replace("https://gitlab.com/", "registry.gitlab.com/")
    
    if env == "dev":
        return f"""\
# {app_name} Dev Surcharges
# Ce fichier est mis à jour automatiquement par le pipeline GitLab CI
# lors de chaque push sur une branche release-dev-*.
replicas: 1

image:
  repository: {image_repository}
  tag: "none"
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
    - host: {app_name}-dev.cri.epita.fr
      paths:
        - path: /
          pathType: ImplementationSpecific
"""
    else:  # prod
        return f"""\
# {app_name} Prod Surcharges
replicas: 3

image:
  repository: {image_repository}
  tag: "none"
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
    gitops_project_path = urllib.parse.urlparse(settings.GITOPS_REPO_URL).path.lstrip("/").removesuffix(".git")
    
    actions = []
    
    # "upsert" creates the file if absent, overwrites if present — one atomic commit either
    # way. This makes provisioning idempotent: safe to retry or re-onboard without errors.
    for file_path, content in [
        (f"argocd/{app_name}/dev.yaml",       _generate_argocd_application(app_name, repo_url, "dev")),
        (f"argocd/{app_name}/prod.yaml",      _generate_argocd_application(app_name, repo_url, "prod")),
        (f"apps/{app_name}/values-dev.yaml",  _generate_helm_values(app_name, repo_url, "dev")),
        (f"apps/{app_name}/values-prod.yaml", _generate_helm_values(app_name, repo_url, "prod")),
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
