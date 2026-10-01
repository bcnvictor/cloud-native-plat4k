#!/usr/bin/env python3
"""Local smoke test for the Keycloak app-auth service (4K-15/ADR-0026, plan Lot 7).

Exercises KeycloakService.provision/status/reprovision against a REAL local
Keycloak + Vault (docker compose, profile production), end to end:

  1. provision(app, "dev") -> verifies the realm, the client, and the audience
     protocol mapper actually exist in Keycloak, and that OIDC_* landed in Vault.
  2. Obtains a real access token via client_credentials against the freshly
     provisioned confidential client, and validates it with the python-fastapi
     template's own auth.py (get_current_user) — the same code a scaffolded app
     would run.
  3. Deletes the realm directly (simulating a team deleting it via the console),
     checks status() reports it missing, then reprovision()s it.
  4. Cleans up (deletes both dev/prod realms and the Vault path) unless --keep.

Prerequisites (see docker-compose.yml / infra/keycloak/README.md):
  docker compose --profile production up -d db vault keycloak
  # Vault must be initialized+unsealed, KV v2 enabled at "secret/" (see README)
  ./scripts/keycloak-bootstrap-local.sh   # creates the cnp-provisioner client

Usage:
  KEYCLOAK_ADMIN_CLIENT_SECRET=<from bootstrap script> \
  VAULT_TOKEN=<vault root token> \
  python3 scripts/keycloak-smoke.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Must be set before backend.core.config is imported (Settings() runs at import time).
os.environ.setdefault("SECRET_KEY", "smoke-test-secret-key-at-least-32-chars!!")
os.environ.setdefault("POSTGRES_SERVER", "localhost")
os.environ.setdefault("POSTGRES_USER", "smoke")
os.environ.setdefault("POSTGRES_PASSWORD", "smoke")
os.environ.setdefault("POSTGRES_DB", "smoke")
os.environ.setdefault("ENCRYPTION_KEY", "")
os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("VAULT_ADDR", "http://127.0.0.1:8200")

import httpx  # noqa: E402

from backend.core.config import settings  # noqa: E402
from backend.db.models import Application  # noqa: E402
from backend.services.keycloak_service import KeycloakService, realm_name  # noqa: E402
from backend.vault.client import vault_client  # noqa: E402

KEEP = "--keep" in sys.argv[1:]
APP_SLUG = "smoke-kc-app"
VAULT_PATH = f"apps/_ungrouped/{APP_SLUG}/dev"


def _configure_settings() -> None:
    settings_client_id = os.environ.get("KEYCLOAK_ADMIN_CLIENT_ID", "cnp-provisioner")
    settings_client_secret = os.environ.get("KEYCLOAK_ADMIN_CLIENT_SECRET")
    if not settings_client_secret:
        print(
            "ERROR: set KEYCLOAK_ADMIN_CLIENT_SECRET (printed by "
            "scripts/keycloak-bootstrap-local.sh).",
            file=sys.stderr,
        )
        sys.exit(1)

    object.__setattr__(settings, "KEYCLOAK_ENABLED", True)
    object.__setattr__(settings, "KEYCLOAK_URL", os.environ.get("KEYCLOAK_URL", "http://localhost:8081"))
    object.__setattr__(settings, "KEYCLOAK_PUBLIC_URL", os.environ.get("KEYCLOAK_PUBLIC_URL", "http://localhost:8081"))
    object.__setattr__(settings, "KEYCLOAK_ADMIN_CLIENT_ID", settings_client_id)
    object.__setattr__(settings, "KEYCLOAK_ADMIN_CLIENT_SECRET", settings_client_secret)

    object.__setattr__(vault_client, "_client", None)
    object.__setattr__(settings, "VAULT_ADDR", os.environ.get("VAULT_ADDR", "http://127.0.0.1:8200"))
    vault_token = os.environ.get("VAULT_TOKEN")
    if not vault_token:
        print("ERROR: set VAULT_TOKEN (the Vault root/unseal-time token).", file=sys.stderr)
        sys.exit(1)
    object.__setattr__(settings, "VAULT_TOKEN", vault_token)


def _step(msg: str) -> None:
    print(f"\n=== {msg} ===")


async def _admin_get(path: str) -> httpx.Response:
    """Raw Admin API call reusing KeycloakService's own client, for assertions the
    service layer doesn't expose a method for (e.g. reading a client's mappers)."""
    service = KeycloakService(db=None)
    client = service._client()
    token = await client._get_token()
    async with httpx.AsyncClient(base_url=settings.KEYCLOAK_URL, timeout=10) as http:
        return await http.get(path, headers={"Authorization": f"Bearer {token}"})


async def main() -> int:
    _configure_settings()
    app = Application(
        id=1, name="Smoke KC App", slug=APP_SLUG, owner="smoke-test",
        framework="python-fastapi", expose=False, owning_gitlab_group_id=None,
        auth_enabled=False, auth_warnings=None,
    )
    service = KeycloakService(db=None)
    realm = realm_name(APP_SLUG, "dev")

    try:
        _step(f"1. provision(app, 'dev') -> realm '{realm}'")
        result = await service.provision(app, "dev")
        assert result.exists, "provision() reports the realm does not exist"
        print(f"OK: realm exists, issuer_url={result.issuer_url}")

        _step("1b. verify realm + client + audience mapper via the Admin API")
        resp = await _admin_get(f"/admin/realms/{realm}")
        assert resp.status_code == 200, f"realm GET failed: {resp.status_code} {resp.text}"
        print(f"OK: GET /admin/realms/{realm} -> 200")

        resp = await _admin_get(f"/admin/realms/{realm}/clients?clientId={APP_SLUG}")
        clients = resp.json()
        assert clients, "app client not found in realm"
        client_internal_id = clients[0]["id"]
        assert clients[0]["publicClient"] is False, "expected a confidential client (framework=python-fastapi)"
        assert clients[0]["webOrigins"][0] == "+", f"webOrigins should start with '+', got {clients[0]['webOrigins']}"
        print(f"OK: client '{APP_SLUG}' exists, id={client_internal_id}, confidential")

        resp = await _admin_get(f"/admin/realms/{realm}/clients/{client_internal_id}/protocol-mappers/models")
        mappers = resp.json()
        audience_mapper = next((m for m in mappers if m["name"] == "audience"), None)
        assert audience_mapper is not None, "audience protocol mapper missing"
        assert audience_mapper["config"]["included.client.audience"] == APP_SLUG
        print(f"OK: audience protocol mapper present, included.client.audience={APP_SLUG}")

        _step("1c. verify OIDC_* landed in Vault")
        secret = vault_client.get_secret(VAULT_PATH)
        assert secret["OIDC_ISSUER_URL"] == result.issuer_url
        assert secret["OIDC_CLIENT_ID"] == APP_SLUG
        client_secret = secret["OIDC_CLIENT_SECRET"]
        print(f"OK: Vault {VAULT_PATH} has OIDC_ISSUER_URL/OIDC_CLIENT_ID/OIDC_CLIENT_SECRET")

        _step("2. obtain a real access token (client_credentials) and validate it")
        async with httpx.AsyncClient(base_url=settings.KEYCLOAK_URL, timeout=10) as http:
            token_resp = await http.post(
                f"/realms/{realm}/protocol/openid-connect/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": APP_SLUG,
                    "client_secret": client_secret,
                },
            )
        assert token_resp.status_code == 200, f"token request failed: {token_resp.text}"
        access_token = token_resp.json()["access_token"]
        print("OK: obtained access token via client_credentials")

        # Validate with the actual python-fastapi template's auth.py — the same
        # code a scaffolded app runs. Set env vars BEFORE importing it (module-level
        # PyJWKClient is built once at import time).
        template_src = REPO_ROOT.parent / "cnp-templates" / "python-fastapi" / "src"
        if not template_src.is_dir():
            print(f"SKIP: template validation — {template_src} not found (expected sibling repo checkout)")
        else:
            os.environ["OIDC_ISSUER_URL"] = result.issuer_url
            os.environ["OIDC_CLIENT_ID"] = APP_SLUG
            sys.path.insert(0, str(template_src.parent))
            sys.modules.pop("src.auth", None)
            sys.modules.pop("src", None)
            from src.auth import get_current_user  # type: ignore

            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            tmp_app = FastAPI()

            @tmp_app.get("/me")
            def me(user=None):
                return {"sub": user["sub"]} if user else {}

            # Call the dependency directly rather than wiring a full route, to keep
            # this script decoupled from FastAPI's DI machinery version quirks.
            from fastapi.security import HTTPAuthorizationCredentials

            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=access_token)
            claims = await get_current_user(credentials=creds)
            assert claims["sub"], "decoded token has no 'sub' claim"
            print(f"OK: python-fastapi template's get_current_user() accepted the token (sub={claims['sub']})")
            del tmp_app, TestClient  # unused, kept for readability of intent above

        _step("2b. grant_console_access(): tagged CNP account, never an end user's")
        from backend.db.models import User

        console_user = User(id=4242, email="alice@example.com", hashed_password="x")
        creds = await service.grant_console_access(app, "dev", console_user)
        assert creds.username == "cnp.alice.4242", creds.username
        resp = await _admin_get(f"/admin/realms/{realm}/users?q=cnp_user_id:4242&exact=true")
        tagged = [u for u in resp.json() if "4242" in (u.get("attributes") or {}).get("cnp_user_id", [])]
        assert len(tagged) == 1, f"console account not found by attribute: {resp.json()}"
        print("OK: console account created and found by its cnp_user_id attribute")

        await service.revoke_member(app, 4242)
        resp = await _admin_get(f"/admin/realms/{realm}/users?q=cnp_user_id:4242&exact=true")
        assert not resp.json(), "console account still present after revoke_member()"
        print("OK: revoke_member() removed the console account")

        _step("3. delete_realm() directly (simulating a team deleting their realm)")
        client = service._client()
        await client.delete_realm(realm)
        status_after_delete = await service.status(app)
        assert status_after_delete.dev.state == "missing", status_after_delete.dev.state
        print("OK: status().dev.state == 'missing' after direct deletion")

        _step("3b. reprovision(app, 'dev') recreates it")
        result2 = await service.reprovision(app, "dev")
        assert result2.exists is True
        print(f"OK: reprovision() recreated '{realm}'")

        _step("SMOKE TEST PASSED")
        return 0
    finally:
        if not KEEP:
            _step("cleanup")
            try:
                await service.deprovision(app)
                print(f"OK: deleted realms {realm_name(APP_SLUG, 'dev')} / {realm_name(APP_SLUG, 'prod')}")
            except Exception as e:
                print(f"WARN: deprovision failed (manual cleanup may be needed): {e}")
            try:
                vault_client.delete_secret(VAULT_PATH)
                print(f"OK: deleted Vault path {VAULT_PATH}")
            except Exception as e:
                print(f"WARN: failed to delete Vault path {VAULT_PATH}: {e}")
        else:
            print("\n--keep passed: realm and Vault secret left in place.")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
