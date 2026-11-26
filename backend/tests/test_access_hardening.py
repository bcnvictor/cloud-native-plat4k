"""4K-47: access gaps found while mapping the DevSecOps posture (docs/devsecops.md §5.2).

- non-members get no tier, so no app detail (ADR-0017 §7);
- deleting an app is Owner only (ADR-0017 §5);
- the admin override on env vars is audited, and the audit row survives a read-only route;
- password login is rate limited.
"""
from unittest.mock import AsyncMock, patch

import pytest
from shared.models import MemberStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.rate_limit import LOGIN_RATE_LIMIT
from backend.db.models import Application, AppMember, AuditLog, ClusterConnection, User
from backend.vault.client import vault_client

pytestmark = pytest.mark.anyio

PROJECT_ID = 5150


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def app_row(db_session: AsyncSession) -> Application:
    cluster = ClusterConnection(name="aks", endpoint="https://x", kubeconfig_secret_ref="ref")
    db_session.add(cluster)
    await db_session.flush()
    application = Application(
        name="hardened", slug="hardened", owner="team/x",
        target_cluster_id=cluster.id, gitlab_project_id=PROJECT_ID,
    )
    db_session.add(application)
    await db_session.commit()
    await db_session.refresh(application)
    return application


async def _make_member(db_session: AsyncSession, user: User, access_level: int) -> None:
    db_session.add(AppMember(
        gitlab_project_id=PROJECT_ID, gitlab_user_id=1000 + user.id, access_level=access_level,
        cnp_user_id=user.id, status=MemberStatus.ACTIVE,
    ))
    await db_session.commit()


# ── non-members ───────────────────────────────────────────────────────────────


async def test_non_member_cannot_read_viewer_routes(client, dev_token, app_row):
    resp = await client.get(f"/api/v1/apps/{app_row.id}/members", headers=_auth(dev_token))
    assert resp.status_code == 403


async def test_reporter_member_can_read_viewer_routes(client, db_session, dev_user, dev_token, app_row):
    await _make_member(db_session, dev_user, 20)
    resp = await client.get(f"/api/v1/apps/{app_row.id}/members", headers=_auth(dev_token))
    assert resp.status_code == 200


# ── delete: Owner only ────────────────────────────────────────────────────────


@pytest.mark.parametrize("access_level, expected", [(40, 403), (50, 200)])
async def test_delete_app_requires_owner(client, db_session, dev_user, dev_token, app_row, access_level, expected):
    await _make_member(db_session, dev_user, access_level)
    with patch("backend.api.routes.apps.AppService.delete_app", AsyncMock()) as delete, \
         patch("backend.api.routes.apps.emit_event", AsyncMock()):
        resp = await client.delete(f"/api/v1/apps/{app_row.id}", headers=_auth(dev_token))
    assert resp.status_code == expected
    assert delete.await_count == (1 if expected == 200 else 0)


# ── admin bypass on env vars ──────────────────────────────────────────────────


async def test_admin_bypass_on_env_vars_is_audited_and_committed(
    client, db_session, admin_user, admin_token, app_row, monkeypatch
):
    monkeypatch.setattr(vault_client, "get_secret", lambda path, mount_point="secret": {"K": "v"})
    app_id, admin_id = app_row.id, admin_user.id
    resp = await client.get(f"/api/v1/apps/{app_id}/env/prod", headers=_auth(admin_token))
    assert resp.status_code == 200

    # Read-only route: nothing commits after the check. The audit row must already be
    # committed, so it survives the rollback that closing the session amounts to.
    await db_session.rollback()
    rows = (await db_session.execute(
        select(AuditLog).where(AuditLog.app_id == app_id, AuditLog.user_id == admin_id)
    )).scalars().all()
    assert [r.action for r in rows] == ["ADMIN_BYPASS_TIER:maintainer"]


# ── login rate limit ──────────────────────────────────────────────────────────


async def test_password_login_is_rate_limited_per_client_ip(client, dev_user):
    limit = int(LOGIN_RATE_LIMIT.split("/")[0])
    bad = {"username": "dev@test.com", "password": "wrong"}
    for _ in range(limit):
        resp = await client.post("/api/v1/auth/login", data=bad, headers={"CF-Connecting-IP": "203.0.113.7"})
        assert resp.status_code == 401
    resp = await client.post("/api/v1/auth/login", data=bad, headers={"CF-Connecting-IP": "203.0.113.7"})
    assert resp.status_code == 429

    # Another client is not affected by the first one's attempts
    resp = await client.post(
        "/api/v1/auth/login", data={"username": "dev@test.com", "password": "devpass123"},
        headers={"CF-Connecting-IP": "198.51.100.9"},
    )
    assert resp.status_code == 200
