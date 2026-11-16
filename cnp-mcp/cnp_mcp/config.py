import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    api_url: str
    api_key: str | None
    allowed_hosts: list[str]
    port: int


def _expand_hosts(raw: str) -> list[str]:
    # La lib compare le Host exact : "localhost" ne couvre pas "localhost:8080".
    hosts = [h.strip() for h in raw.split(",") if h.strip()]
    return [value for host in hosts for value in (host, f"{host}:*")]


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    api_url = env.get("CNP_API_URL", "").strip().rstrip("/")
    if not api_url:
        raise RuntimeError("CNP_API_URL is required")
    return Settings(
        api_url=api_url,
        api_key=env.get("CNP_API_KEY", "").strip() or None,
        allowed_hosts=_expand_hosts(env.get("MCP_ALLOWED_HOSTS", "localhost,127.0.0.1")),
        port=int(env.get("MCP_PORT", "8080")),
    )
