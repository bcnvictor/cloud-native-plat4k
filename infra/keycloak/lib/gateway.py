"""Operator-only gateway configuration. Never imported by the backend."""

import secrets
import shlex
from contextlib import contextmanager
from pathlib import Path

from .commands import run
from .config import TargetConfig


def render_route(target: TargetConfig) -> str:
    template = (Path(__file__).resolve().parents[1] / "gateway/route.conf.template").read_text()
    return (
        template.replace("@KEY@", target.instance_key)
        .replace("@TAILNET@", target.tailnet_domain)
        .replace("@DOMAIN@", target.public_domain)
    )


@contextmanager
def install_route(target: TargetConfig, config: bytes):
    """Retain the previous route until public verification and CNP activation."""
    transaction = secrets.token_hex(16)

    def command(action, payload=None):
        remote = f"cd {shlex.quote(target.gateway_repo_path)} && bash infra/keycloak/gateway/apply-route.sh {shlex.quote(target.instance_key)} {action} {transaction}"
        return run(["ssh", "-o", "BatchMode=yes", target.gateway_host, remote], stdin=payload)

    try:
        command("stage", config)
    except RuntimeError:
        # SSH may have disconnected after staging; attempt an ownership-checked
        # restoration. A foreign lock is never removed.
        try:
            command("rollback")
        except RuntimeError:
            pass
        raise
    try:
        yield
    except BaseException:
        command("rollback")
        raise
    else:
        command("commit")
