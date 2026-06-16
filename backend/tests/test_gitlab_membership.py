"""
Tests for:
  4K-65 — data model (GitLabGroup, GitLabGroupMember, AppMember)
  4K-66 — sync service reconciliation logic
  4K-67 — authorization tiers (get_effective_tier, require_tier, /my-access, /admin/sync-gitlab)
"""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars!")
os.environ.setdefault("POSTGRES_SERVER", "localhost")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("ENCRYPTION_KEY", "")

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from shared.models import ApplicationStatus, CnpTier, MemberStatus, UserRole
from sqlalchemy import select

from backend.api.deps import _access_level_to_tier, get_effective_tier
from backend.core.security import get_password_hash
from backend.db.models import Application, AppMember, GitLabGroup, GitLabGroupMember, User
from backend.db.session import get_db
from backend.main import app
from backend.services.gitlab_sync_service import _sync_group, _sync_project, run_gitlab_sync

# ── helpers ───────────────────────────────────────────────────────────────────

async def _fake_to_thread(fn, *args, **kwargs):
    """Drop-in for asyncio.to_thread that runs synchronously in tests."""
    return fn(*args, **kwargs)


def _make_gl_member(gl_id: int, access_level: int):
    m = MagicMock()
    m.id = gl_id
    m.access_level = access_level
    return m


def _make_gl_invitation(email: str, access_level: int = 30):
    inv = MagicMock()
    inv.invite_email = email
    inv.access_level = access_level
    return inv


# ── local fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
async def is_admin_user(db_session):
    user = User(
        email="superadmin@test.com",
        hashed_password=get_password_hash("superpass123"),
        role=UserRole.ADMIN,
        is_active=True,
        is_admin=True,
        gitlab_user_id=999,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def regular_user(db_session):
    user = User(
        email="regular@test.com",
        hashed_password=get_password_hash("pass123"),
        role=UserRole.DEV,
        is_active=True,
        is_admin=False,
        gitlab_user_id=100,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def app_with_project(db_session) -> Application:
    application = Application(
        name="test-app",
        slug="test-app",
        owner="team-x",
        gitlab_project_id=42,
        status=ApplicationStatus.READY,
    )
    db_session.add(application)
    await db_session.commit()
    await db_session.refresh(application)
    return application


@pytest.fixture
async def app_without_project(db_session) -> Application:
    application = Application(
        name="app-no-gl",
        slug="app-no-gl",
        owner="team-y",
        status=ApplicationStatus.READY,
    )
    db_session.add(application)
    await db_session.commit()
    await db_session.refresh(application)
    return application


@pytest.fixture
async def gitlab_group(db_session) -> GitLabGroup:
    group = GitLabGroup(gitlab_group_id=10, name="my-group", full_path="org/my-group")
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)
    return group


@pytest.fixture
def client_with_db(db_session):
    """Client fixture — avoids re-importing the session-scoped one from conftest."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return db_session


async def _token_for(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# ══════════════════════════════════════════════════════════════════════════════
# 4K-67 — tier mapping (pure unit, no DB)
# ══════════════════════════════════════════════════════════════════════════════

class TestAccessLevelToTier:
    def test_guest_is_viewer(self):
        assert _access_level_to_tier(10) == CnpTier.VIEWER

    def test_reporter_is_viewer(self):
        assert _access_level_to_tier(20) == CnpTier.VIEWER

    def test_developer(self):
        assert _access_level_to_tier(30) == CnpTier.DEVELOPER

    def test_maintainer(self):
        assert _access_level_to_tier(40) == CnpTier.MAINTAINER

    def test_owner(self):
        assert _access_level_to_tier(50) == CnpTier.OWNER

    def test_above_owner_still_owner(self):
        assert _access_level_to_tier(99) == CnpTier.OWNER


# ══════════════════════════════════════════════════════════════════════════════
# 4K-67 — get_effective_tier (needs DB)
# ══════════════════════════════════════════════════════════════════════════════

class TestGetEffectiveTier:
    async def test_no_app_members_returns_viewer(self, db_session, regular_user, app_with_project):
        tier = await get_effective_tier(regular_user.id, app_with_project.id, db_session)
        assert tier == CnpTier.VIEWER

    async def test_app_without_gitlab_project_returns_viewer(self, db_session, regular_user, app_without_project):
        tier = await get_effective_tier(regular_user.id, app_without_project.id, db_session)
        assert tier == CnpTier.VIEWER

    async def test_developer_access_level(self, db_session, regular_user, app_with_project):
        db_session.add(AppMember(
            gitlab_project_id=app_with_project.gitlab_project_id,
            gitlab_user_id=regular_user.gitlab_user_id,
            access_level=30,
            cnp_user_id=regular_user.id,
            status=MemberStatus.ACTIVE,
        ))
        await db_session.commit()

        tier = await get_effective_tier(regular_user.id, app_with_project.id, db_session)
        assert tier == CnpTier.DEVELOPER

    async def test_maintainer_access_level(self, db_session, regular_user, app_with_project):
        db_session.add(AppMember(
            gitlab_project_id=app_with_project.gitlab_project_id,
            gitlab_user_id=regular_user.gitlab_user_id,
            access_level=40,
            cnp_user_id=regular_user.id,
            status=MemberStatus.ACTIVE,
        ))
        await db_session.commit()

        tier = await get_effective_tier(regular_user.id, app_with_project.id, db_session)
        assert tier == CnpTier.MAINTAINER

    async def test_left_member_returns_viewer(self, db_session, regular_user, app_with_project):
        """Soft-revoked member (status=left) must not grant any tier."""
        db_session.add(AppMember(
            gitlab_project_id=app_with_project.gitlab_project_id,
            gitlab_user_id=regular_user.gitlab_user_id,
            access_level=50,
            cnp_user_id=regular_user.id,
            status=MemberStatus.LEFT,
        ))
        await db_session.commit()

        tier = await get_effective_tier(regular_user.id, app_with_project.id, db_session)
        assert tier == CnpTier.VIEWER


# ══════════════════════════════════════════════════════════════════════════════
# 4K-67 — GET /apps/{id}/my-access
# ══════════════════════════════════════════════════════════════════════════════

class TestMyAccess:
    async def test_returns_viewer_when_no_membership(
        self, client, db_session, app_with_project, regular_user
    ):
        token = await _token_for(client, "regular@test.com", "pass123")
        resp = await client.get(
            f"/api/v1/apps/{app_with_project.id}/my-access",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["tier"] == "viewer"
        assert body["is_admin"] is False

    async def test_returns_is_admin_true_for_admin(
        self, client, db_session, app_with_project, is_admin_user
    ):
        token = await _token_for(client, "superadmin@test.com", "superpass123")
        resp = await client.get(
            f"/api/v1/apps/{app_with_project.id}/my-access",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_admin"] is True

    async def test_returns_correct_tier_from_app_members(
        self, client, db_session, app_with_project, regular_user
    ):
        db_session.add(AppMember(
            gitlab_project_id=app_with_project.gitlab_project_id,
            access_level=40,
            cnp_user_id=regular_user.id,
            status=MemberStatus.ACTIVE,
        ))
        await db_session.commit()

        token = await _token_for(client, "regular@test.com", "pass123")
        resp = await client.get(
            f"/api/v1/apps/{app_with_project.id}/my-access",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["tier"] == "maintainer"

    async def test_unauthenticated_returns_401(self, client, app_with_project):
        resp = await client.get(f"/api/v1/apps/{app_with_project.id}/my-access")
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# 4K-67 — POST /admin/sync-gitlab (auth guard)
# ══════════════════════════════════════════════════════════════════════════════

class TestAdminSyncGitlab:
    async def test_non_admin_gets_403(self, client, regular_user):
        token = await _token_for(client, "regular@test.com", "pass123")
        resp = await client.post(
            "/api/v1/admin/sync-gitlab",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_unauthenticated_gets_401(self, client):
        resp = await client.post("/api/v1/admin/sync-gitlab")
        assert resp.status_code == 401

    async def test_is_admin_triggers_sync(self, client, db_session, is_admin_user):
        token = await _token_for(client, "superadmin@test.com", "superpass123")
        # No token configured → sync skips gracefully
        with patch("backend.services.gitlab_sync_service.settings") as mock_settings:
            mock_settings.GITLAB_BOT_TOKEN = None
            mock_settings.GITLAB_TOKEN = None
            mock_settings.GITLAB_BASE_URL = "https://gitlab.com"
            resp = await client.post(
                "/api/v1/admin/sync-gitlab",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        assert resp.json().get("skipped") is True


# ══════════════════════════════════════════════════════════════════════════════
# 4K-66 — sync service reconciliation
# ══════════════════════════════════════════════════════════════════════════════

class TestSyncGroup:
    async def test_creates_new_member(self, db_session, gitlab_group):
        gl_group_mock = MagicMock()
        gl_group_mock.members_all.list.return_value = [_make_gl_member(gl_id=7, access_level=40)]
        gl = MagicMock()
        gl.groups.get.return_value = gl_group_mock

        with patch("backend.services.gitlab_sync_service.asyncio.to_thread", new=_fake_to_thread):
            stats = await _sync_group(db_session, gl, gitlab_group)

        assert stats["created"] == 1
        assert stats["updated"] == 0
        assert stats["revoked"] == 0

        result = await db_session.execute(
            select(GitLabGroupMember).where(GitLabGroupMember.gitlab_group_id == 10)
        )
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].gitlab_user_id == 7
        assert rows[0].access_level == 40
        assert rows[0].status == MemberStatus.ACTIVE

    async def test_updates_existing_member(self, db_session, gitlab_group):
        db_session.add(GitLabGroupMember(
            gitlab_group_id=10, gitlab_user_id=7, access_level=30, status=MemberStatus.ACTIVE
        ))
        await db_session.commit()

        gl_group_mock = MagicMock()
        gl_group_mock.members_all.list.return_value = [_make_gl_member(gl_id=7, access_level=40)]
        gl = MagicMock()
        gl.groups.get.return_value = gl_group_mock

        with patch("backend.services.gitlab_sync_service.asyncio.to_thread", new=_fake_to_thread):
            stats = await _sync_group(db_session, gl, gitlab_group)

        assert stats["updated"] == 1
        assert stats["created"] == 0

        result = await db_session.execute(
            select(GitLabGroupMember).where(GitLabGroupMember.gitlab_user_id == 7)
        )
        assert result.scalar_one().access_level == 40

    async def test_soft_revokes_absent_member(self, db_session, gitlab_group):
        """Member no longer in GitLab must become LEFT, not be deleted."""
        db_session.add(GitLabGroupMember(
            gitlab_group_id=10, gitlab_user_id=7, access_level=40, status=MemberStatus.ACTIVE
        ))
        await db_session.commit()

        gl_group_mock = MagicMock()
        gl_group_mock.members_all.list.return_value = []  # member gone from GitLab
        gl = MagicMock()
        gl.groups.get.return_value = gl_group_mock

        with patch("backend.services.gitlab_sync_service.asyncio.to_thread", new=_fake_to_thread):
            stats = await _sync_group(db_session, gl, gitlab_group)

        assert stats["revoked"] == 1

        result = await db_session.execute(
            select(GitLabGroupMember).where(GitLabGroupMember.gitlab_user_id == 7)
        )
        row = result.scalar_one()
        assert row.status == MemberStatus.LEFT   # soft-revoke, row still exists
        assert row.gitlab_user_id == 7           # never deleted

    async def test_links_cnp_user_id_on_upsert(self, db_session, gitlab_group, regular_user):
        """User with gitlab_user_id=100 should be linked via cnp_user_id."""
        gl_group_mock = MagicMock()
        gl_group_mock.members_all.list.return_value = [_make_gl_member(gl_id=100, access_level=30)]
        gl = MagicMock()
        gl.groups.get.return_value = gl_group_mock

        with patch("backend.services.gitlab_sync_service.asyncio.to_thread", new=_fake_to_thread):
            await _sync_group(db_session, gl, gitlab_group)

        result = await db_session.execute(
            select(GitLabGroupMember).where(GitLabGroupMember.gitlab_user_id == 100)
        )
        row = result.scalar_one()
        assert row.cnp_user_id == regular_user.id


class TestSyncProject:
    async def test_creates_active_member(self, db_session, app_with_project):
        gl_project_mock = MagicMock()
        gl_project_mock.members_all.list.return_value = [_make_gl_member(gl_id=7, access_level=30)]
        gl_project_mock.invitations.list.return_value = []
        gl = MagicMock()
        gl.projects.get.return_value = gl_project_mock

        with patch("backend.services.gitlab_sync_service.asyncio.to_thread", new=_fake_to_thread):
            stats = await _sync_project(db_session, gl, app_with_project)

        assert stats["created"] == 1
        result = await db_session.execute(
            select(AppMember).where(AppMember.gitlab_project_id == 42)
        )
        row = result.scalar_one()
        assert row.status == MemberStatus.ACTIVE

    async def test_creates_pending_invite(self, db_session, app_with_project):
        gl_project_mock = MagicMock()
        gl_project_mock.members_all.list.return_value = []
        gl_project_mock.invitations.list.return_value = [
            _make_gl_invitation("new@user.com", access_level=30)
        ]
        gl = MagicMock()
        gl.projects.get.return_value = gl_project_mock

        with patch("backend.services.gitlab_sync_service.asyncio.to_thread", new=_fake_to_thread):
            stats = await _sync_project(db_session, gl, app_with_project)

        assert stats["created"] == 1
        result = await db_session.execute(
            select(AppMember).where(AppMember.gitlab_project_id == 42)
        )
        row = result.scalar_one()
        assert row.status == MemberStatus.PENDING_INVITE
        assert row.email == "new@user.com"
        assert row.gitlab_user_id is None

    async def test_pending_invite_not_revoked_while_in_list(self, db_session, app_with_project):
        """PENDING_INVITE must never become LEFT while the invite still exists in GitLab."""
        db_session.add(AppMember(
            gitlab_project_id=42, email="invited@user.com",
            access_level=30, status=MemberStatus.PENDING_INVITE,
        ))
        await db_session.commit()

        gl_project_mock = MagicMock()
        gl_project_mock.members_all.list.return_value = []
        gl_project_mock.invitations.list.return_value = [
            _make_gl_invitation("invited@user.com")
        ]
        gl = MagicMock()
        gl.projects.get.return_value = gl_project_mock

        with patch("backend.services.gitlab_sync_service.asyncio.to_thread", new=_fake_to_thread):
            await _sync_project(db_session, gl, app_with_project)

        result = await db_session.execute(
            select(AppMember).where(AppMember.email == "invited@user.com")
        )
        assert result.scalar_one().status == MemberStatus.PENDING_INVITE

    async def test_pending_invite_revoked_when_removed(self, db_session, app_with_project):
        """PENDING_INVITE becomes LEFT when invitation disappears from GitLab."""
        db_session.add(AppMember(
            gitlab_project_id=42, email="old@user.com",
            access_level=30, status=MemberStatus.PENDING_INVITE,
        ))
        await db_session.commit()

        gl_project_mock = MagicMock()
        gl_project_mock.members_all.list.return_value = []
        gl_project_mock.invitations.list.return_value = []  # invite cancelled in GitLab
        gl = MagicMock()
        gl.projects.get.return_value = gl_project_mock

        with patch("backend.services.gitlab_sync_service.asyncio.to_thread", new=_fake_to_thread):
            stats = await _sync_project(db_session, gl, app_with_project)

        assert stats["revoked"] == 1
        result = await db_session.execute(
            select(AppMember).where(AppMember.email == "old@user.com")
        )
        assert result.scalar_one().status == MemberStatus.LEFT

    async def test_soft_revokes_active_member_gone_from_gitlab(self, db_session, app_with_project):
        db_session.add(AppMember(
            gitlab_project_id=42, gitlab_user_id=77,
            access_level=40, status=MemberStatus.ACTIVE,
        ))
        await db_session.commit()

        gl_project_mock = MagicMock()
        gl_project_mock.members_all.list.return_value = []
        gl_project_mock.invitations.list.return_value = []
        gl = MagicMock()
        gl.projects.get.return_value = gl_project_mock

        with patch("backend.services.gitlab_sync_service.asyncio.to_thread", new=_fake_to_thread):
            stats = await _sync_project(db_session, gl, app_with_project)

        assert stats["revoked"] == 1
        result = await db_session.execute(
            select(AppMember).where(AppMember.gitlab_user_id == 77)
        )
        row = result.scalar_one()
        assert row.status == MemberStatus.LEFT
        assert row.gitlab_user_id == 77  # still present (no hard-delete)


class TestRunGitlabSync:
    async def test_skips_when_no_token(self, db_session):
        with patch("backend.services.gitlab_sync_service.settings") as s:
            s.GITLAB_BOT_TOKEN = None
            s.GITLAB_TOKEN = None
            result = await run_gitlab_sync(db_session)
        assert result == {"skipped": True}

    async def test_syncs_groups_and_projects(self, db_session, gitlab_group, app_with_project):
        gl_group_mock = MagicMock()
        gl_group_mock.members_all.list.return_value = [_make_gl_member(gl_id=5, access_level=30)]
        gl_project_mock = MagicMock()
        gl_project_mock.members_all.list.return_value = [_make_gl_member(gl_id=6, access_level=40)]
        gl_project_mock.invitations.list.return_value = []

        gl_mock = MagicMock()
        gl_mock.groups.get.return_value = gl_group_mock
        gl_mock.projects.get.return_value = gl_project_mock

        with (
            patch("backend.services.gitlab_sync_service._build_gitlab_client", return_value=gl_mock),
            patch("backend.services.gitlab_sync_service.asyncio.to_thread", new=_fake_to_thread),
        ):
            result = await run_gitlab_sync(db_session)

        assert result["groups"]["created"] == 1
        assert result["projects"]["created"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# 4K-67 — JWT contains is_admin
# ══════════════════════════════════════════════════════════════════════════════

class TestJwtPayload:
    async def test_jwt_contains_is_admin_false(self, client, regular_user):
        from jose import jwt as jose_jwt

        from backend.core.config import settings

        token = await _token_for(client, "regular@test.com", "pass123")
        payload = jose_jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert "is_admin" in payload
        assert payload["is_admin"] is False

    async def test_jwt_contains_is_admin_true(self, client, is_admin_user):
        from jose import jwt as jose_jwt

        from backend.core.config import settings

        token = await _token_for(client, "superadmin@test.com", "superpass123")
        payload = jose_jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert payload["is_admin"] is True
