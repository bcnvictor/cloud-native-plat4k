"""Exhaustive tier matrix for /api/v1/apps/{id}/env/{env}/* routes (4K-248).

Complements test_env_var_routes.py: every (principal, env, operation) pair is
checked against the ADR-0025 §3 matrix, for both sources of effective tier
(GitLab project membership and owning-group membership). A refused call must
leave the fake Vault untouched; only GET /env/dev/values may return values.
"""

import copy
import itertools

import pytest
from httpx import AsyncClient
from hvac.exceptions import InvalidPath
from shared.models import MemberStatus, UserRole

from backend.db.models import (
    Application,
    AppMember,
    ClusterConnection,
    GitLabGroup,
    GitLabGroupMember,
    User,
)
from backend.services.auth_service import AuthService
from backend.vault.client import vault_client

pytestmark = pytest.mark.asyncio

PROJECT_ID = 1001
GROUP_ID = 2001
GROUP_PATH = "team/t248"
APP_SLUG = "matrix-app"
SECRET_VALUE = "s3cr3t-value-must-not-leak"

# Principal -> GitLab access level (None = no membership at all).
ACCESS_LEVELS = {
    "none": None,
    "reporter": 20,
    "developer": 30,
    "maintainer": 40,
    "owner": 50,
}
PRINCIPALS = [*ACCESS_LEVELS, "admin"]
OPERATIONS = ["list", "status", "put", "delete", "values"]

_READ_OK_DEV = set(PRINCIPALS)
_WRITE_OK_DEV = {"developer", "maintainer", "owner", "admin"}
_ALL_OK_PROD = {"maintainer", "owner", "admin"}


def _expected_status(principal: str, env: str, op: str) -> int:
    """ADR-0025 §3 + 4K-107 addendum, written out independently of the route code."""
    if op == "values":
        return 200 if env == "dev" and principal in _WRITE_OK_DEV else 403
    if env == "prod":
        return 200 if principal in _ALL_OK_PROD else 403
    allowed = _READ_OK_DEV if op in ("list", "status") else _WRITE_OK_DEV
    return 200 if principal in allowed else 403


def _vault_path(env: str) -> str:
    return f"apps/{GROUP_PATH}/{APP_SLUG}/{env}"


@pytest.fixture(autouse=True)
def fake_vault(monkeypatch):
    """In-memory KV v2 seeded with one key per env, recording every write."""
    store: dict[str, dict[str, str]] = {
        _vault_path("dev"): {"EXISTING": SECRET_VALUE},
        _vault_path("prod"): {"EXISTING": SECRET_VALUE},
    }
    writes: list[tuple] = []

    def fake_get_secret(path, mount_point="secret"):
        if path not in store:
            raise InvalidPath(f"no data at {path}")
        return dict(store[path])

    def fake_patch_secret(path, secret, mount_point="secret"):
        writes.append(("patch", path, dict(secret)))
        store.setdefault(path, {}).update(secret)

    def fake_delete_secret_key(path, key, mount_point="secret"):
        writes.append(("delete_key", path, key))
        store.get(path, {}).pop(key, None)

    def fake_delete_secret(path, mount_point="secret"):
        writes.append(("delete", path))
        store.pop(path, None)

    monkeypatch.setattr(vault_client, "get_secret", fake_get_secret)
    monkeypatch.setattr(vault_client, "patch_secret", fake_patch_secret)
    monkeypatch.setattr(vault_client, "delete_secret_key", fake_delete_secret_key)
    monkeypatch.setattr(vault_client, "delete_secret", fake_delete_secret)
    return {"store": store, "writes": writes}


@pytest.fixture
async def matrix_app(db_session) -> Application:
    """App attached to both a GitLab project and an owning group, so either
    membership source can grant the tier under test."""
    cluster = ClusterConnection(name="aks", endpoint="https://x", kubeconfig_secret_ref="ref")
    db_session.add(cluster)
    db_session.add(GitLabGroup(gitlab_group_id=GROUP_ID, name="t248", full_path=GROUP_PATH))
    await db_session.flush()
    application = Application(
        name=APP_SLUG,
        slug=APP_SLUG,
        owner=GROUP_PATH,
        target_cluster_id=cluster.id,
        gitlab_project_id=PROJECT_ID,
        owning_gitlab_group_id=GROUP_ID,
    )
    db_session.add(application)
    await db_session.commit()
    await db_session.refresh(application)
    return application


@pytest.fixture
def login_as(db_session, matrix_app: Application):
    """Create a user for `principal`, grant its access level through `source`
    ("project" or "group") with `status`, and return auth headers. The token is
    issued by AuthService like /auth/login, minus the bcrypt cost per case."""

    async def _login(principal: str, source: str = "project", status: MemberStatus = MemberStatus.ACTIVE) -> dict:
        user = User(
            email=f"{principal}-{source}-{status.value}@test.com",
            hashed_password="unused",
            role=UserRole.ADMIN if principal == "admin" else UserRole.DEV,
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        level = ACCESS_LEVELS.get(principal)
        if level is not None and source == "project":
            db_session.add(AppMember(
                gitlab_project_id=PROJECT_ID, gitlab_user_id=user.id + 5000,
                cnp_user_id=user.id, access_level=level, status=status,
            ))
        elif level is not None and source == "group":
            db_session.add(GitLabGroupMember(
                gitlab_group_id=GROUP_ID, gitlab_user_id=user.id + 5000,
                cnp_user_id=user.id, access_level=level, status=status,
            ))
        await db_session.commit()

        access_token, _ = AuthService(db_session).create_tokens(user)
        return {"Authorization": f"Bearer {access_token}"}

    return _login


async def _call(client: AsyncClient, app_id: int, env: str, op: str, headers: dict):
    base = f"/api/v1/apps/{app_id}/env/{env}"
    if op == "list":
        return await client.get(base, headers=headers)
    if op == "status":
        return await client.get(f"{base}/EXISTING/status", headers=headers)
    if op == "put":
        return await client.put(base, json={"variables": {"NEW_KEY": "new-value"}}, headers=headers)
    if op == "delete":
        return await client.delete(f"{base}/EXISTING", headers=headers)
    if op == "values":
        return await client.get(f"{base}/values", headers=headers)
    raise AssertionError(op)


def _assert_outcome(resp, principal: str, env: str, op: str, fake_vault, store_before: dict) -> None:
    expected = _expected_status(principal, env, op)
    assert resp.status_code == expected, f"{principal} {op} {env}: {resp.status_code} {resp.text}"

    if expected == 403:
        assert fake_vault["writes"] == [], f"refused {op} on {env} still wrote to Vault"
        assert fake_vault["store"] == store_before

    # matrix_app has Keycloak disabled (auth_enabled=False): no key is managed.
    if op == "list" and expected == 200:
        assert resp.json()["keys"] == [{"key": "EXISTING", "is_set": True, "managed": False}]
    if op == "put" and expected == 200:
        assert resp.json()["keys"] == [
            {"key": "EXISTING", "is_set": True, "managed": False},
            {"key": "NEW_KEY", "is_set": True, "managed": False},
        ]

    if op == "values" and expected == 200:
        assert resp.json() == {"EXISTING": SECRET_VALUE}
    else:
        # Write-only contract: no other endpoint, allowed or refused, leaks a value.
        assert SECRET_VALUE not in resp.text


MATRIX = list(itertools.product(PRINCIPALS, ["dev", "prod"], OPERATIONS))


class TestTierMatrixProjectMembership:
    @pytest.mark.parametrize("principal,env,op", MATRIX)
    async def test_matrix(self, client, matrix_app, login_as, fake_vault, principal, env, op):
        headers = await login_as(principal, source="project")
        before = copy.deepcopy(fake_vault["store"])
        resp = await _call(client, matrix_app.id, env, op, headers)
        _assert_outcome(resp, principal, env, op, fake_vault, before)


class TestTierMatrixGroupMembership:
    """Same matrix when the tier only comes from the owning GitLab group
    (scaffolded apps before project membership is mirrored)."""

    GROUP_PRINCIPALS = ["reporter", "developer", "maintainer", "owner"]

    @pytest.mark.parametrize(
        "principal,env,op", list(itertools.product(GROUP_PRINCIPALS, ["dev", "prod"], OPERATIONS))
    )
    async def test_matrix(self, client, matrix_app, login_as, fake_vault, principal, env, op):
        headers = await login_as(principal, source="group")
        before = copy.deepcopy(fake_vault["store"])
        resp = await _call(client, matrix_app.id, env, op, headers)
        _assert_outcome(resp, principal, env, op, fake_vault, before)


class TestInactiveMembership:
    """A maintainer-level membership that is not ACTIVE must count as no membership."""

    @pytest.mark.parametrize("status", [MemberStatus.LEFT, MemberStatus.PENDING_INVITE])
    @pytest.mark.parametrize("source", ["project", "group"])
    @pytest.mark.parametrize("env,op", [("prod", "list"), ("prod", "put"), ("dev", "put"), ("dev", "values")])
    async def test_inactive_member_treated_as_viewer(
        self, client, matrix_app, login_as, fake_vault, status, source, env, op
    ):
        headers = await login_as("maintainer", source=source, status=status)
        before = copy.deepcopy(fake_vault["store"])
        resp = await _call(client, matrix_app.id, env, op, headers)
        assert resp.status_code == 403, resp.text
        assert fake_vault["writes"] == []
        assert fake_vault["store"] == before


class TestValuesLock:
    """GET /env/{env}/values is the only value-returning endpoint and must stay
    locked to exactly 'dev' (4K-107 addendum) — `cnp env pull` relies on it."""

    ENV_VARIANTS = ["prod", "PROD", "Prod", "prod%20", "dev%20", "DEV", "Dev", "staging", "dev%2Fvalues"]

    @pytest.mark.parametrize("principal", ["maintainer", "owner", "admin"])
    @pytest.mark.parametrize("env", ENV_VARIANTS)
    async def test_only_exact_dev_returns_values(self, client, matrix_app, login_as, principal, env):
        headers = await login_as(principal)
        resp = await client.get(f"/api/v1/apps/{matrix_app.id}/env/{env}/values", headers=headers)
        assert resp.status_code in (403, 404, 405, 422), f"{env}: {resp.status_code} {resp.text}"
        assert SECRET_VALUE not in resp.text

    @pytest.mark.parametrize("principal", ["developer", "maintainer", "admin"])
    @pytest.mark.parametrize("env", ["PROD", "Prod", "prod%20"])
    async def test_prod_case_variants_do_not_bypass_prod_gate(self, client, matrix_app, login_as, principal, env):
        """Non-canonical spellings of prod must never reach Vault's prod path."""
        headers = await login_as(principal)
        resp = await client.get(f"/api/v1/apps/{matrix_app.id}/env/{env}", headers=headers)
        assert resp.status_code in (403, 422), resp.text
        assert "EXISTING" not in resp.text

    async def test_values_reads_the_dev_path_only(self, client, matrix_app, login_as, fake_vault):
        fake_vault["store"][_vault_path("dev")] = {"ONLY_DEV": "dev-value"}
        headers = await login_as("developer")
        resp = await client.get(f"/api/v1/apps/{matrix_app.id}/env/dev/values", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == {"ONLY_DEV": "dev-value"}
        assert SECRET_VALUE not in resp.text

    async def test_values_unknown_app_does_not_leak(self, client, matrix_app, login_as):
        headers = await login_as("admin")
        resp = await client.get("/api/v1/apps/999999/env/dev/values", headers=headers)
        assert resp.status_code == 404
        assert SECRET_VALUE not in resp.text
