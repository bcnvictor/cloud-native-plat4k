"""Deterministic "fix prompt" templates for the Security tab (Mode A, no LLM).

The prompt is meant to be pasted in the user's own coding agent at the root of the cloned
repo. It never contains a secret value (the backend does not have it) and goes through
ai.redaction as a safety net.
"""
from __future__ import annotations

from typing import Any, Optional

from backend.ai.redaction import redact

MAX_LISTED = 20  # findings detailed in a "fix all" prompt

_COMMON_TASK = """\
## Task
- Make the smallest change that fixes it. Do not refactor or touch unrelated code.
- Work on a dedicated branch (e.g. `{branch}`), commit with a clear message, then open a Merge Request.
- Run the project's existing tests and linter before committing, and make sure they pass.
- Do NOT modify `.gitlab-ci.yml` nor any file managed by CNP (generated Dockerfile, `chart/`, CI includes).
- If you are unsure, or if the tests break and you cannot fix them cleanly, stop and explain instead of forcing a fix.
"""


def _context(app, report) -> str:
    return (
        "## Context\n"
        f"- Application: {app.name} (`{app.slug}`)\n"
        f"- Repository: {app.repo_url or 'unknown'} (work from the default branch)\n"
        f"- Security pipeline: {report.pipeline_url} (commit `{report.commit_sha[:8]}`)\n"
    )


def _success(finding_ids: list[str]) -> str:
    ids = ", ".join(f"`{i}`" for i in finding_ids)
    return (
        "## Success criterion\n"
        f"On the next pipeline of the default branch, the finding id(s) {ids} must no longer appear "
        "in the CNP Security tab.\n"
    )


def _dependency(f: dict[str, Any]) -> str:
    fixed = f.get("fixed_version")
    target = (
        f"upgrade `{f.get('package')}` from `{f.get('installed_version')}` to `{fixed}` (or the closest safe version)"
        if fixed
        else f"no fixed version is published for `{f.get('package')}` `{f.get('installed_version')}`: "
        "propose a safe alternative (other package or version) and explain the trade-off"
    )
    return (
        f"- Tool: trivy (dependency vulnerability)\n"
        f"- Identifier: {f['rule']}  (finding id: `{f['id']}`)\n"
        f"- Severity: {f['severity']}\n"
        f"- Package: `{f.get('package')}` — installed `{f.get('installed_version')}` → fixed `{fixed or 'none'}`\n"
        f"- File: `{f.get('file')}`\n"
        f"- Action: {target}. Update the lockfile too if the project has one.\n"
    )


def _secret(f: dict[str, Any]) -> str:
    where = f"{f.get('file')}:{f.get('line')}" if f.get("line") else f"{f.get('file')}"
    return (
        f"- Tool: gitleaks (secret detection)\n"
        f"- Rule: {f['rule']}  (finding id: `{f['id']}`)\n"
        f"- Location: `{where}`\n"
        "- Action: remove the secret from the code and read it from an environment variable "
        "(or a Vault reference) instead. The value is intentionally not given to you.\n"
    )


_SECRET_WARNING = (
    "> **WARNING — the secret is already compromised.** It remains in the git history and must be "
    "revoked / rotated at its provider. Removing it from the code is not enough.\n\n"
)


def _find(report, finding_id: str) -> Optional[tuple[str, dict[str, Any]]]:
    for tool, data in (report.payload or {}).items():
        for f in (data or {}).get("findings", []):
            if f["id"] == finding_id:
                return tool, f
    return None


def build_fix_prompt(app, report, finding: str) -> Optional[str]:
    """Return the prompt for one finding id or for "all"; None if the finding is unknown/empty."""
    if finding == "all":
        items = [
            (tool, f)
            for tool in ("trivy", "gitleaks")
            for f in ((report.payload or {}).get(tool) or {}).get("findings", [])
        ]
        if not items:
            return None
        total = sum(
            (((report.payload.get(t) or {}).get("counts") or {}).get("total") if t == "gitleaks"
             else sum(((report.payload.get(t) or {}).get("counts") or {}).values()))
            or 0
            for t in ("trivy", "gitleaks")
        )
        total = max(total, len(items))
        shown = items[:MAX_LISTED]
        parts = []
        for n, (tool, f) in enumerate(shown, 1):
            parts.append(f"### Finding {n}\n" + (_dependency(f) if tool == "trivy" else _secret(f)))
        extra = total - len(shown)
        if extra > 0:
            parts.append(f"… and {extra} other finding(s) not listed here; fix these first, then re-check the Security tab.\n")
        head = _SECRET_WARNING if any(t == "gitleaks" for t, _ in shown) else ""
        text = (
            f"{head}You are fixing security findings reported by CNP for this repository.\n\n"
            + _context(app, report) + "\n## Findings\n" + "\n".join(parts) + "\n"
            + _COMMON_TASK.format(branch="cnp/security-fixes") + "\n"
            + _success([f["id"] for _, f in shown])
        )
    else:
        hit = _find(report, finding)
        if hit is None:
            return None
        tool, f = hit
        head = _SECRET_WARNING if tool == "gitleaks" else ""
        text = (
            f"{head}You are fixing a security finding reported by CNP for this repository.\n\n"
            + _context(app, report) + "\n## Finding\n" + (_dependency(f) if tool == "trivy" else _secret(f)) + "\n"
            + _COMMON_TASK.format(branch=f"cnp/fix-{f['id']}") + "\n"
            + _success([f["id"]])
        )
    return redact(text).text
