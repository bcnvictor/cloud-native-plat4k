"""Generate an Application only for a published, immutable platform commit."""
import argparse
import os
from pathlib import Path

import yaml
from infra.keycloak.lib.config import ROOT, load_target
from infra.keycloak.lib.http_api import JSONAPI


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    import re
    if not re.fullmatch(r"[a-f0-9]{40}", args.revision):
        parser.error("A full immutable Git SHA is required")
    target = load_target(args.config)
    headers = {}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    commit = JSONAPI("https://api.github.com", headers).request("GET", f"/repos/bcnvictor/cloud-native-plat4k/commits/{args.revision}")
    if commit["sha"] != args.revision:
        raise RuntimeError("Chart commit is not published")
    image_lock = yaml.safe_load((ROOT / "images.lock.yaml").read_text())
    application = {"apiVersion": "argoproj.io/v1alpha1", "kind": "Application", "metadata": {"name": target.argo_application or f"keycloak-{target.instance_key}", "namespace": "argocd"}, "spec": {"project": "default", "source": {"repoURL": "https://github.com/bcnvictor/cloud-native-plat4k.git", "targetRevision": args.revision, "path": "infra/keycloak/chart", "helm": {"releaseName": target.release, "valuesObject": target.helm_values(image_lock)}}, "destination": {"server": "https://kubernetes.default.svc", "namespace": target.namespace}, "syncPolicy": {"syncOptions": ["CreateNamespace=true"]}}}
    print(yaml.safe_dump(application, sort_keys=False))


if __name__ == "__main__":
    main()
