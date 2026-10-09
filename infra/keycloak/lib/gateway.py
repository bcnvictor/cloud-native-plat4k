"""Operator-only gateway configuration. Never imported by the backend."""

import shlex
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


def install_route(target: TargetConfig, config: bytes) -> None:
    command = f"cd {shlex.quote(target.gateway_repo_path)} && bash infra/keycloak/gateway/apply-route.sh {shlex.quote(target.instance_key)}"
    run(["ssh", "-o", "BatchMode=yes", target.gateway_host, command], stdin=config)
