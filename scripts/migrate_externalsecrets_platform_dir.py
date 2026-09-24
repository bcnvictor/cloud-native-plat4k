#!/usr/bin/env python3
"""One-shot migration for cnp-gitops: move ExternalSecret manifests from the dead
`apps/{cluster}/{app}/externalsecret-{env}.yaml` location to the location ArgoCD
actually deploys, `apps/{cluster}/{app}/platform/{env}/externalsecret.yaml`, and add
the matching 3rd Helm source to each existing Application manifest under `argocd/`.

Context (4K-15 / ADR-0026 Lot 1c, see also the ADR-0024 addendum): the root-app only
scans `argocd/`, and an Application's `ref: gitops` source only resolves `valueFiles`
— it deploys no manifest. `cnp-ci-modules/base/pipeline.yml` (`update-gitops`) now
writes new ExternalSecret manifests under `platform/{env}/` and wires the 3rd source
automatically for every future CI run, including retrofitting it onto Applications it
encounters that don't have it yet. This script is only needed for the files/commits
that already exist in cnp-gitops from *before* that fix shipped, and won't get another
`update-gitops` run soon (e.g. an app whose CI never runs again).

USAGE
    python3 scripts/migrate_externalsecrets_platform_dir.py /path/to/local/cnp-gitops-clone
    python3 scripts/migrate_externalsecrets_platform_dir.py /path/to/clone --execute

Safety:
  - Dry-run by default: prints a plan, changes nothing on disk.
  - --execute actually moves files / rewrites YAML in the clone's working tree.
  - This script NEVER runs `git commit`, `git push`, or touches a remote — review
    `git status`/`git diff` in the clone and commit/push yourself.
  - Only ever run this against a disposable local clone, never a checked-out copy of
    cnp-gitops you also use for other work, and never directly against the real repo
    without reviewing the diff first.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

LEGACY_RE = re.compile(
    r"^apps/(?P<cluster>[^/]+)/(?P<app>[^/]+)/externalsecret-(?P<env>dev|prod)\.yaml$"
)


def find_legacy_files(root: Path):
    for p in sorted(root.glob("apps/*/*/externalsecret-*.yaml")):
        rel = p.relative_to(root).as_posix()
        m = LEGACY_RE.match(rel)
        if m:
            yield p, m.group("cluster"), m.group("app"), m.group("env")


def new_path_for(root: Path, cluster: str, app: str, env: str) -> Path:
    return root / "apps" / cluster / app / "platform" / env / "externalsecret.yaml"


def app_manifest_path(root: Path, cluster: str, app: str, env: str) -> Path:
    return root / "argocd" / cluster / app / f"{env}.yaml"


def ensure_platform_source(
    manifest_path: Path, cluster: str, app: str, env: str, gitops_url: str, execute: bool
) -> str:
    if not manifest_path.exists():
        return "SKIP (Application manifest not found)"
    data = yaml.safe_load(manifest_path.read_text()) or {}
    spec = data.setdefault("spec", {})
    sources = spec.get("sources", [])
    platform_path = f"apps/{cluster}/{app}/platform/{env}"
    if any(s.get("path") == platform_path for s in sources):
        return "already present"
    if execute:
        sources.append(
            {"repoURL": gitops_url, "targetRevision": "HEAD", "path": platform_path}
        )
        spec["sources"] = sources
        manifest_path.write_text(
            yaml.safe_dump(data, default_flow_style=False, sort_keys=False)
        )
    return "added" if execute else "would add"


def resolve_gitops_url(root: Path, override: str | None) -> str:
    if override:
        return override
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "remote", "get-url", "origin"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "<GITOPS_REPO_URL>"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("gitops_clone", type=Path, help="Path to a local clone of cnp-gitops")
    parser.add_argument(
        "--execute", action="store_true", help="Actually perform the migration (default: dry-run)"
    )
    parser.add_argument(
        "--gitops-url",
        default=None,
        help="repoURL for the new source (default: `git remote get-url origin` in the clone)",
    )
    args = parser.parse_args()

    root = args.gitops_clone.resolve()
    if not root.is_dir():
        print(f"ERROR: {root} is not a directory", file=sys.stderr)
        return 1
    if not (root / ".git").exists():
        print(f"ERROR: {root} does not look like a git clone (no .git)", file=sys.stderr)
        return 1

    gitops_url = resolve_gitops_url(root, args.gitops_url)
    legacy = list(find_legacy_files(root))
    if not legacy:
        print("No legacy externalsecret-{env}.yaml files found — nothing to do.")
        return 0

    print(f"{'EXECUTING' if args.execute else 'DRY RUN'} — gitops clone: {root}")
    print(f"gitops repoURL for new sources: {gitops_url}\n")

    for old_path, cluster, app, env in legacy:
        new_path = new_path_for(root, cluster, app, env)
        rel_old = old_path.relative_to(root)
        rel_new = new_path.relative_to(root)
        print(f"[{cluster}/{app}/{env}] {rel_old} -> {rel_new}")
        if args.execute:
            new_path.parent.mkdir(parents=True, exist_ok=True)
            old_path.replace(new_path)

        manifest_path = app_manifest_path(root, cluster, app, env)
        status = ensure_platform_source(manifest_path, cluster, app, env, gitops_url, args.execute)
        print(f"    Application source ({manifest_path.relative_to(root)}): {status}")

    if not args.execute:
        print(
            "\nDry-run only — re-run with --execute to apply, then review `git status`/"
            "`git diff` in the clone and commit/push yourself. This script never commits "
            "or pushes."
        )
    else:
        print(
            "\nDone. Review `git status`/`git diff` in the clone, then commit and push "
            "yourself."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
