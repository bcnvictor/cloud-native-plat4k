"""Disposable, real-service validation. No import-time process or network effects."""

import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import httpx
import yaml
from infra.keycloak.lib.config import ROOT, TargetConfig, load_target
from infra.keycloak.lib.gateway import render_route
from infra.keycloak.lib.http_api import JSONAPI
from infra.keycloak.lib.keycloak_api import KeycloakAdmin
from infra.keycloak.lib.vault_api import VaultAPI

REPO = ROOT.parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def checked(argv, *, env=None):
    result = subprocess.run(argv, env=env, capture_output=True)
    if result.returncode:
        # Logs from live services may include tokens; preserve no exception body.
        diagnostic = result.stderr.decode(errors="replace")
        for key, value in (env or {}).items():
            if (
                any(part in key for part in ("TOKEN", "PASSWORD", "SECRET", "KEY"))
                and len(value) > 4
            ):
                diagnostic = diagnostic.replace(value, "[redacted]")
        raise RuntimeError("Integration command failed: " + argv[0] + "\n" + diagnostic[-3000:])
    return result


@contextmanager
def local_stack():
    images = yaml.safe_load((ROOT / "images.lock.yaml").read_text())
    with tempfile.TemporaryDirectory(prefix="cnp-keycloak-real-") as folder:
        path = Path(folder)
        (path / "routes").mkdir()
        certs = path / "certs/live/localhost"
        certs.mkdir(parents=True)
        checked(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=DNS:localhost,IP:127.0.0.1",
                "-keyout",
                str(certs / "privkey.pem"),
                "-out",
                str(certs / "fullchain.pem"),
            ]
        )
        ports = {name: free_port() for name in ("gateway", "public", "private", "vault", "cnp_db")}
        credentials = {
            "database": secrets.token_hex(16),
            "bootstrap": secrets.token_hex(16),
            "vault": secrets.token_hex(16),
        }
        env = os.environ | {
            "TEST_DIRECTORY": folder,
            "TEST_DB_PASSWORD": credentials["database"],
            "TEST_BOOTSTRAP_PASSWORD": credentials["bootstrap"],
            "TEST_VAULT_TOKEN": credentials["vault"],
        }
        for name, port in ports.items():
            env[f"TEST_{name.upper()}_PORT"] = str(port)
        for name, image in images.items():
            env[f"TEST_{'POSTGRES' if name == 'postgresql' else name.upper()}_IMAGE"] = image
        target = TargetConfig(
            "public-01",
            "public",
            "local-test",
            "local-test",
            "localhost",
            "integration.test",
            "local-path",
            "local-test",
        )
        for key in ("public-01", "private-01"):
            (path / "routes" / f"{key}.conf").write_text(
                render_route(replace(target, instance_key=key))
            )
        vhost = (
            (ROOT / "gateway/auth.conf.template").read_text().replace("${AUTH_DOMAIN}", "localhost")
        )
        (path / "nginx.conf").write_text("events {} http { " + vhost + " }")
        project = "cnp-keycloak-real-" + secrets.token_hex(5)
        base = [
            "docker",
            "compose",
            "--env-file",
            "/dev/null",
            "-p",
            project,
            "-f",
            str(ROOT / "tests/compose.yaml"),
        ]
        state = {
            "ports": ports,
            "credentials": credentials,
            "project": project,
            "database_url": f"postgresql+asyncpg://cnp:{credentials['database']}@127.0.0.1:{ports['cnp_db']}/cnp_keycloak_test",
            "vault_url": f"http://127.0.0.1:{ports['vault']}",
            "public_base": f"https://localhost:{ports['gateway']}",
        }
        for name, key in (("public", "public-01"), ("private", "private-01")):
            state[name] = {
                "key": key,
                "admin_url": f"http://127.0.0.1:{ports[name]}/clusters/{key}",
                "public_url": state["public_base"] + f"/clusters/{key}",
            }
        state_path = path / "state.json"
        state_path.touch(mode=0o600)
        state_path.write_text(json.dumps(state))
        try:
            print("Starting isolated Keycloak integration stack", flush=True)
            checked([*base, "up", "-d"], env=env)
            deadline = time.monotonic() + 600
            pending = {"public", "private"}
            while pending and time.monotonic() < deadline:
                for name in tuple(pending):
                    try:
                        JSONAPI(state[name]["admin_url"]).request(
                            "GET", "/realms/master/.well-known/openid-configuration"
                        )
                        pending.remove(name)
                    except RuntimeError:
                        pass
                if pending:
                    time.sleep(2)
            if pending:
                # Only infrastructure logs; callers may inspect containers while
                # running. Never dump credentials in a failure traceback.
                raise RuntimeError("Keycloak readiness timed out")
            yield state, state_path
        finally:
            checked([*base, "down", "--volumes", "--remove-orphans"], env=env)


def admin(state, name):
    return KeycloakAdmin(
        state[name]["admin_url"], "cnp-bootstrap", state["credentials"]["bootstrap"]
    )


def verify_bootstrap(state):
    vault = VaultAPI(state["vault_url"], state["credentials"]["vault"])
    for name in ("public", "private"):
        from infra.keycloak.lib.http_api import APIError

        key = state[name]["key"]
        first_credentials = vault.ensure_secret(
            f"cnp/keycloak/{key}/bootstrap",
            {"username": "cnp-bootstrap", "password": state["credentials"]["bootstrap"]},
        )
        assert (
            vault.ensure_secret(f"cnp/keycloak/{key}/bootstrap", {"password": "must-not-rotate"})
            == first_credentials
        )
        token = vault.ensure_eso_token(key)
        assert vault.ensure_eso_token(key) == token
        reader = VaultAPI(state["vault_url"], token)
        reader.request("GET", f"/v1/secret/data/cnp/keycloak/{key}/bootstrap")
        for forbidden in (f"cnp/keycloak/{key}/provisioner", "apps/demo/dev", "cnp/platform"):
            try:
                reader.request("GET", "/v1/secret/data/" + forbidden)
            except APIError as error:
                assert error.status == 403
            else:
                raise AssertionError("ESO identity escaped its dedicated secret scope")
        first = admin(state, name).ensure_provisioner()
        second = admin(state, name).ensure_provisioner()
        assert first == second
        vault.store_provisioner(state[name]["key"], first)
        vault.store_provisioner(state[name]["key"], second)
        admin(state, name).verify_public_issuer(state[name]["public_url"])
        state[name]["provisioner_secret"] = first
    # bootstrap secrets remain private; browser setup uses the same file.


async def verify_migration(state):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(state["database_url"])
    env = os.environ | {
        "SECRET_KEY": "integration-only-key-32characters",
        "POSTGRES_SERVER": "127.0.0.1",
        "POSTGRES_PORT": str(state["ports"]["cnp_db"]),
        "POSTGRES_USER": "cnp",
        "POSTGRES_PASSWORD": state["credentials"]["database"],
        "POSTGRES_DB": "cnp_keycloak_test",
    }
    try:
        checked(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "backend/alembic.ini",
                "upgrade",
                "b1c2d3e4f5a6",
            ],
            env=env,
        )
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO applications (id,name,slug,owner,auth_enabled,last_known_status) VALUES (9900,'legacy','integration-legacy','test',true,'onboarding')"
                )
            )
        checked(
            [sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"],
            env=env,
        )
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text("SELECT auth_enabled,auth_instance_key FROM applications WHERE id=9900")
                )
            ).one()
            assert row.auth_enabled is True and row.auth_instance_key is None
    finally:
        await engine.dispose()


async def verify_lifecycle(state, monkeypatch):
    import hvac
    from backend.core.config import settings
    from backend.db.models import Application, ClusterConnection
    from backend.services.keycloak_instance_service import KeycloakInstanceService
    from backend.services.keycloak_service import KeycloakService
    from backend.vault.client import vault_client
    from shared.models import KeycloakInstanceUpsert
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    monkeypatch.setattr(settings, "KEYCLOAK_ENABLED", False)
    monkeypatch.setattr(
        vault_client,
        "_client",
        hvac.Client(url=state["vault_url"], token=state["credentials"]["vault"], timeout=10),
    )
    engine = create_async_engine(state["database_url"])
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            for index, name in enumerate(("public", "private"), 1):
                cluster = ClusterConnection(
                    id=index,
                    name=f"integration-{name}",
                    endpoint="https://test.invalid",
                    kubeconfig_secret_ref="test",
                )
                session.add(cluster)
            await session.commit()
            for index, name in enumerate(("public", "private"), 1):
                item = state[name]
                await KeycloakInstanceService(session).upsert(
                    item["key"],
                    KeycloakInstanceUpsert(
                        cluster_id=index,
                        public_url=item["public_url"],
                        admin_url=item["admin_url"],
                        admin_client_id="cnp-provisioner",
                        provisioner_secret_ref=f"cnp/keycloak/{item['key']}/provisioner",
                        enabled=True,
                    ),
                )
                framework = "react-vite" if index == 1 else "python-fastapi"
                app = Application(
                    id=100 + index,
                    name=f"integration-{name}",
                    slug=f"integration-{name}",
                    owner="test",
                    framework=framework,
                    target_cluster_id=index,
                    expose=False,
                )
                session.add(app)
                await session.commit()
                service = KeycloakService(session)
                result = await service.activate(app)
                assert result.auth_provisioned is True
                assert app.auth_instance_key == item["key"]
                variables = vault_client.get_secret(f"apps/_ungrouped/{app.slug}/dev")
                assert (
                    variables["OIDC_ISSUER_URL"] == item["public_url"] + f"/realms/{app.slug}-dev"
                )
                assert ("OIDC_CLIENT_SECRET" in variables) == (framework != "react-vite")
                other = admin(state, "private" if name == "public" else "public")
                assert (
                    other.request("GET", f"/admin/realms/{app.slug}-dev", missing_ok=True) is None
                )
                own = admin(state, name)
                clients = own.request(
                    "GET", f"/admin/realms/{app.slug}-dev/clients?clientId={app.slug}"
                )
                assert clients[0]["publicClient"] is (framework == "react-vite")
                if framework == "react-vite":
                    assert clients[0]["attributes"]["pkce.code.challenge.method"] == "S256"
                # Durable binding still routes the same issuer after app retarget.
                app.target_cluster_id = 2 if index == 1 else 1
                await session.commit()
                assert (await service.status(app)).dev.issuer_url == variables["OIDC_ISSUER_URL"]
            from jose import JWTError, jwt

            private_base = state["private"]["admin_url"]
            private_issuer = state["private"]["public_url"] + "/realms/integration-private-dev"
            confidential = vault_client.get_secret("apps/_ungrouped/integration-private/dev")
            token = JSONAPI(private_base).request(
                "POST",
                "/realms/integration-private-dev/protocol/openid-connect/token",
                {
                    "grant_type": "client_credentials",
                    "client_id": "integration-private",
                    "client_secret": confidential["OIDC_CLIENT_SECRET"],
                },
                form=True,
            )["access_token"]
            keys = JSONAPI(private_base).request(
                "GET", "/realms/integration-private-dev/protocol/openid-connect/certs"
            )
            claims = jwt.decode(
                token,
                keys,
                algorithms=["RS256"],
                audience="integration-private",
                issuer=private_issuer,
            )
            assert "integration-private" in claims["aud"]
            for invalid in (
                {"audience": "other-app", "issuer": private_issuer},
                {
                    "audience": "integration-private",
                    "issuer": state["public"]["public_url"] + "/realms/integration-public-dev",
                },
            ):
                try:
                    jwt.decode(token, keys, algorithms=["RS256"], **invalid)
                except JWTError:
                    pass
                else:
                    raise AssertionError("Wrong audience/issuer JWT was accepted")
            # Test cleanup of a distinct owned app; keep browser realms until stack teardown.
            app = Application(
                id=103,
                name="cleanup",
                slug="integration-cleanup",
                owner="test",
                framework="python-fastapi",
                target_cluster_id=2,
                expose=False,
            )
            session.add(app)
            await session.commit()
            service = KeycloakService(session)
            assert (await service.activate(app)).auth_provisioned is True
            await service.deprovision(app)
            assert (
                admin(state, "private").request(
                    "GET", "/admin/realms/integration-cleanup-dev", missing_ok=True
                )
                is None
            )
    finally:
        await engine.dispose()


def create_browser_user(state, name, realm, username, password):
    own = admin(state, name)
    own.request(
        "POST",
        f"/admin/realms/{realm}/users",
        {
            "username": username,
            "enabled": True,
            "email": username + "@integration.test",
            "emailVerified": True,
            "firstName": "Integration",
            "lastName": "Test",
            "credentials": [{"type": "password", "value": password, "temporary": False}],
        },
    )


def verify_browser(state):
    password = secrets.token_hex(16)
    create_browser_user(state, "public", "integration-public-dev", "browser-user", password)
    vault = VaultAPI(state["vault_url"], state["credentials"]["vault"])
    secret = vault.request("GET", "/v1/secret/data/apps/_ungrouped/integration-private/dev")[
        "data"
    ]["data"]["OIDC_CLIENT_SECRET"]
    other_token = JSONAPI(state["private"]["admin_url"]).request(
        "POST",
        "/realms/integration-private-dev/protocol/openid-connect/token",
        {
            "grant_type": "client_credentials",
            "client_id": "integration-private",
            "client_secret": secret,
        },
        form=True,
    )["access_token"]
    payload = {
        "otherToken": other_token,
        "issuer": state["public"]["public_url"] + "/realms/integration-public-dev",
        "otherIssuer": state["private"]["public_url"] + "/realms/integration-private-dev",
        "clientId": "integration-public",
        "username": "browser-user",
        "password": password,
    }
    result = subprocess.run(
        ["node", str(ROOT / "tests/browser-smoke.mjs")],
        input=json.dumps(payload).encode(),
        capture_output=True,
        timeout=120,
    )
    if result.returncode:
        # Helper emits nonsecret diagnostics only; no stdin/tokens in exception.
        raise RuntimeError("Browser authentication smoke failed: " + result.stderr.decode()[-2000:])
    assert json.loads(result.stdout)["passed"] is True


async def verify_console(state, monkeypatch):
    import hvac
    from backend.db.models import Application, User
    from backend.services.keycloak_service import KeycloakService
    from backend.vault.client import vault_client
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    monkeypatch.setattr(
        vault_client,
        "_client",
        hvac.Client(url=state["vault_url"], token=state["credentials"]["vault"], timeout=10),
    )
    engine = create_async_engine(state["database_url"])
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            app = await session.get(Application, 102)
            user = User(
                id=701,
                email="console-team@integration.test",
                hashed_password="not-used-for-keycloak",
            )
            session.add(user)
            await session.commit()
            service = KeycloakService(session)
            access = await service.grant_console_access(app, "dev", user)
            payload = {
                "mode": "console",
                "url": access.console_url,
                "username": access.username,
                "password": access.temporary_password,
                "newPassword": secrets.token_hex(16),
            }
            result = subprocess.run(
                ["node", str(ROOT / "tests/browser-smoke.mjs")],
                input=json.dumps(payload).encode(),
                capture_output=True,
                timeout=120,
            )
            if result.returncode:
                raise RuntimeError(
                    "Team console browser smoke failed: " + result.stderr.decode()[-1500:]
                )
            assert json.loads(result.stdout)["passed"] is True
            await service.revoke_member(app, user.id)
            assert (
                admin(state, "private").request(
                    "GET", "/admin/realms/integration-private-dev/users?username=" + access.username
                )
                == []
            )
    finally:
        await engine.dispose()

    with httpx.Client(verify=False, timeout=15) as client:
        for name in ("public", "private"):
            base = state[name]["public_url"]
            assert client.get(base + f"/admin/integration-{name}-dev/console/").status_code == 200
            for suffix in (
                "/realms/master",
                "/admin/master",
                "/admin/realms/master",
                "/health/ready",
            ):
                assert client.get(base + suffix).status_code == 403


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--local", action="store_true")
    group.add_argument("--target", type=Path)
    args = parser.parse_args()
    if args.target:
        target = load_target(args.target)
        from infra.keycloak.lib.deploy import preflight

        preflight(target)
        # No mutations: check the ready deployment and public master boundaries.
        from infra.keycloak.lib.deploy import kubectl

        kubectl(
            target,
            "-n",
            target.namespace,
            "rollout",
            "status",
            f"deployment/{target.release}-keycloak",
            "--timeout=30s",
        )
        with httpx.Client(timeout=15) as client:
            assert client.get(target.public_url + "/realms/master").status_code == 403
        print("Read-only target checks passed; app login validation remains separate.")
        return
    with local_stack() as (state, path):
        environment = os.environ | {
            "CNP_KEYCLOAK_TEST_STATE": str(path),
            "SSL_CERT_FILE": str(path.parent / "certs/live/localhost/fullchain.pem"),
        }
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "backend/tests/integration/test_keycloak_real.py",
                "-m",
                "keycloak_integration",
                "-q",
                "--disable-warnings",
            ],
            env=environment,
        )
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
