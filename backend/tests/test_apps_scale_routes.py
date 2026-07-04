"""Functional tests for /api/v1/apps/{id}/stop|resume|scale routes (4K-82).

ScaleService.apply_changes is monkeypatched to a DB-only fake (no real GitLab/ArgoCD
calls) — the gitops commit mechanics are covered by test_scale_service.py. These
tests focus on the authorization matrix: MAINTAINER tier is enough for dev,
but prod requires OWNER tier or platform admin.
"""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from shared.models import UserRole
from sqlalchemy import select

from backend.core.security import get_password_hash
from backend.db.models import Application, AppMember, AppScaleState, ClusterConnection, User
from backend.services.scale_service import ScaleService

pytestmark = pytest.mark.asyncio


async def _fake_apply_changes(self, changes, commit_message):
    """DB-only stand-in for ScaleService.apply_changes — skips GitLab/ArgoCD I/O."""
    now = datetime.now(timezone.utc)
    for c in changes:
        state = await self._get_or_create_state(c.app.id, c.env)
        state.is_stopped = c.stopped
        if c.stopped:
            state.stop_reason = c.reason
            state.stopped_at = now
            state.stopped_by_user_id = c.actor_user_id
        else:
            state.stop_reason = None
            state.resumed_at = now
            state.resumed_by_user_id = c.actor_user_id


@pytest.fixture(autouse=True)
def _patch_apply_changes(monkeypatch):
    monkeypatch.setattr(ScaleService, "apply_changes", _fake_apply_changes)


@pytest.fixture
async def cluster(db_session):
    c = ClusterConnection(name="aks", endpoint="https://x", kubeconfig_secret_ref="ref")
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


@pytest.fixture
async def maintainer_user(db_session) -> User:
    user = User(
        email="maintainer@test.com",
        hashed_password=get_password_hash("maintainerpass123"),
        role=UserRole.DEV,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def maintainer_token(client: AsyncClient, maintainer_user: User) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "maintainer@test.com", "password": "maintainerpass123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
async def app_with_maintainer(db_session, cluster, maintainer_user) -> Application:
    """An app where maintainer_user has MAINTAINER tier (access_level=40) — not Owner."""
    application = Application(
        name="demo", slug="demo", owner="o", target_cluster_id=cluster.id, gitlab_project_id=123,
    )
    db_session.add(application)
    await db_session.flush()
    db_session.add(AppMember(
        gitlab_project_id=123, gitlab_user_id=999, cnp_user_id=maintainer_user.id, access_level=40,
    ))
    await db_session.commit()
    await db_session.refresh(application)
    return application


class TestStopApp:
    async def test_stop_dev_as_maintainer_succeeds(
        self, client: AsyncClient, maintainer_token: str, app_with_maintainer: Application, db_session
    ):
        resp = await client.post(
            f"/api/v1/apps/{app_with_maintainer.id}/stop",
            json={"env": "dev"},
            headers={"Authorization": f"Bearer {maintainer_token}"},
        )
        assert resp.status_code == 200

        result = await db_session.execute(
            select(AppScaleState).where(AppScaleState.app_id == app_with_maintainer.id, AppScaleState.env == "dev")
        )
        state = result.scalar_one()
        assert state.is_stopped is True
        assert state.stop_reason.value == "manual"

    async def test_stop_prod_as_maintainer_forbidden(
        self, client: AsyncClient, maintainer_token: str, app_with_maintainer: Application
    ):
        resp = await client.post(
            f"/api/v1/apps/{app_with_maintainer.id}/stop",
            json={"env": "prod"},
            headers={"Authorization": f"Bearer {maintainer_token}"},
        )
        assert resp.status_code == 403

    async def test_stop_both_as_maintainer_forbidden(
        self, client: AsyncClient, maintainer_token: str, app_with_maintainer: Application
    ):
        resp = await client.post(
            f"/api/v1/apps/{app_with_maintainer.id}/stop",
            json={"env": "both"},
            headers={"Authorization": f"Bearer {maintainer_token}"},
        )
        assert resp.status_code == 403

    async def test_stop_prod_as_admin_succeeds(
        self, client: AsyncClient, admin_token: str, app_with_maintainer: Application
    ):
        resp = await client.post(
            f"/api/v1/apps/{app_with_maintainer.id}/stop",
            json={"env": "prod"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200

    async def test_stop_without_membership_forbidden(
        self, client: AsyncClient, dev_token: str, cluster: ClusterConnection, db_session
    ):
        """dev_token's user has no AppMember row on this app -> VIEWER tier -> below MAINTAINER gate."""
        application = Application(name="viewerapp", slug="viewerapp", owner="o", target_cluster_id=cluster.id)
        db_session.add(application)
        await db_session.commit()
        await db_session.refresh(application)

        resp = await client.post(
            f"/api/v1/apps/{application.id}/stop",
            json={"env": "dev"},
            headers={"Authorization": f"Bearer {dev_token}"},
        )
        assert resp.status_code == 403

    async def test_stop_invalid_env_rejected(
        self, client: AsyncClient, maintainer_token: str, app_with_maintainer: Application
    ):
        resp = await client.post(
            f"/api/v1/apps/{app_with_maintainer.id}/stop",
            json={"env": "staging"},
            headers={"Authorization": f"Bearer {maintainer_token}"},
        )
        assert resp.status_code == 422

    async def test_stop_unauthenticated(self, client: AsyncClient, app_with_maintainer: Application):
        resp = await client.post(f"/api/v1/apps/{app_with_maintainer.id}/stop", json={"env": "dev"})
        assert resp.status_code == 401


class TestResumeApp:
    async def test_resume_dev_as_maintainer_succeeds(
        self, client: AsyncClient, maintainer_token: str, app_with_maintainer: Application, db_session
    ):
        # Stop it first so resume has something to clear.
        await client.post(
            f"/api/v1/apps/{app_with_maintainer.id}/stop",
            json={"env": "dev"},
            headers={"Authorization": f"Bearer {maintainer_token}"},
        )

        resp = await client.post(
            f"/api/v1/apps/{app_with_maintainer.id}/resume",
            json={"env": "dev"},
            headers={"Authorization": f"Bearer {maintainer_token}"},
        )
        assert resp.status_code == 200

        result = await db_session.execute(
            select(AppScaleState).where(AppScaleState.app_id == app_with_maintainer.id, AppScaleState.env == "dev")
        )
        state = result.scalar_one()
        assert state.is_stopped is False
        assert state.stop_reason is None

    async def test_resume_prod_as_maintainer_forbidden(
        self, client: AsyncClient, maintainer_token: str, app_with_maintainer: Application
    ):
        resp = await client.post(
            f"/api/v1/apps/{app_with_maintainer.id}/resume",
            json={"env": "prod"},
            headers={"Authorization": f"Bearer {maintainer_token}"},
        )
        assert resp.status_code == 403


class TestGetScaleState:
    async def test_get_scale_state_reflects_stop(
        self, client: AsyncClient, maintainer_token: str, app_with_maintainer: Application
    ):
        await client.post(
            f"/api/v1/apps/{app_with_maintainer.id}/stop",
            json={"env": "dev"},
            headers={"Authorization": f"Bearer {maintainer_token}"},
        )

        resp = await client.get(
            f"/api/v1/apps/{app_with_maintainer.id}/scale",
            headers={"Authorization": f"Bearer {maintainer_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["dev"]["is_stopped"] is True
        assert body["dev"]["stop_reason"] == "manual"
        assert body["prod"] is None
