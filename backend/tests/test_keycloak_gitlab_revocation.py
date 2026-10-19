"""Console access follows the effective tier (4K-15/ADR-0027 §5).

A CNP user keeps a Keycloak console account (realm-admin) only while their effective
tier on the app — best of project and owning-group membership, as in
deps.get_effective_tier — is Maintainer or above. Exercised through the real
triggers: GitLab group and project sync, AppService.add_member, and deactivating the
CNP user. Always best-effort: no Keycloak call while Keycloak is off for the app,
and a Keycloak failure never breaks the caller.
"""
from unittest.mock import MagicMock, patch

import httpx
import pytest
from shared.models import MemberStatus

from backend.core.security import get_password_hash
from backend.db.models import AppMember, GitLabGroup, GitLabGroupMember, User
from backend.keycloak.client import KeycloakClient
from backend.services.app_service import AppService
from backend.services.gitlab_sync_service import _sync_group, _sync_project
from backend.services.keycloak_service import (
    KeycloakService,
    revoke_console_access_if_not_maintainer,
)
from backend.tests.test_keycloak_instance_routing import providers as provider_fixture

providers = provider_fixture

PROJECT_ID = 42
GROUP_ID = 10
GITLAB_USER_ID = 100


async def _fake_to_thread(fn, *args, **kwargs):
    return fn(*args, **kwargs)


def _gl_member(access_level: int):
    member = MagicMock()
    member.id = GITLAB_USER_ID
    member.username = "dev"
    member.access_level = access_level
    return member


def _gl_with(*, group_members=None, project_members=None):
    gl = MagicMock()
    gl.groups.get.return_value.members_all.list.return_value = group_members or []
    gl.projects.get.return_value.members_all.list.return_value = project_members or []
    gl.projects.get.return_value.invitations.list.return_value = []
    return gl


@pytest.fixture
async def setup(providers, db_session):
    """App bound to the private instance, with its GitLab project and owning group,
    and a linked CNP user holding a console account in the prod realm."""
    app, _, fakes, _ = providers
    fake = fakes["private-01"]
    app.gitlab_project_id = PROJECT_ID
    app.owning_gitlab_group_id = GROUP_ID
    group = GitLabGroup(gitlab_group_id=GROUP_ID, name="team", full_path="org/team")
    user = User(
        email="dev@team.test", hashed_password=get_password_hash("x" * 12), is_active=True,
        gitlab_user_id=GITLAB_USER_ID,
    )
    db_session.add_all([group, user])
    await db_session.commit()
    fake.create_realm("commande-prod", {"cnp_app_id": str(app.id)}, id=f"cnp-{app.id}-prod")
    await KeycloakService(db_session).grant_console_access(app, "prod", user)
    assert _console_accounts(fake, user)
    return app, group, user, fake


def _console_accounts(fake, user) -> list[dict]:
    return [
        u for u in fake.realms["commande-prod"]["users"].values()
        if str(user.id) in (u.get("attributes") or {}).get("cnp_user_id", [])
    ]


def _membership(model, user, level, **keys):
    return model(
        gitlab_user_id=GITLAB_USER_ID, cnp_user_id=user.id, access_level=level,
        status=MemberStatus.ACTIVE, **keys,
    )


async def test_gitlab_revocation_uses_bound_instance(providers, db_session, admin_user):
    app, _, fakes, _ = providers
    fake = fakes["private-01"]
    fake.create_realm("commande-prod", {"cnp_app_id": str(app.id)}, id=f"cnp-{app.id}-prod")
    await KeycloakService(db_session).grant_console_access(app, "prod", admin_user)
    await revoke_console_access_if_not_maintainer(db_session, app, admin_user.id)
    assert fake.realms["commande-prod"]["users"] == {}


class TestGroupSync:
    async def test_group_downgrade_below_maintainer_revokes(self, setup, db_session):
        _, group, user, fake = setup
        db_session.add(_membership(GitLabGroupMember, user, 40, gitlab_group_id=GROUP_ID))
        await db_session.commit()

        with patch("backend.services.gitlab_sync_service.asyncio.to_thread", new=_fake_to_thread):
            await _sync_group(db_session, _gl_with(group_members=[_gl_member(30)]), group)

        assert _console_accounts(fake, user) == []

    async def test_leaving_the_group_revokes(self, setup, db_session):
        _, group, user, fake = setup
        db_session.add(_membership(GitLabGroupMember, user, 50, gitlab_group_id=GROUP_ID))
        await db_session.commit()

        with patch("backend.services.gitlab_sync_service.asyncio.to_thread", new=_fake_to_thread):
            await _sync_group(db_session, _gl_with(group_members=[]), group)

        assert _console_accounts(fake, user) == []

    async def test_group_downgrade_revokes_with_production_session_settings(self, setup, db_session):
        """AsyncSessionLocal has autoflush=False: the effective tier must still see the
        membership change the sync has not committed yet."""
        app, group, user, fake = setup
        db_session.add(_membership(GitLabGroupMember, user, 40, gitlab_group_id=GROUP_ID))
        await db_session.commit()
        db_session.sync_session.autoflush = False

        with patch("backend.services.gitlab_sync_service.asyncio.to_thread", new=_fake_to_thread):
            await _sync_group(db_session, _gl_with(group_members=[_gl_member(30)]), group)
            await _sync_project(db_session, _gl_with(project_members=[]), app)

        assert _console_accounts(fake, user) == []

    async def test_group_downgrade_keeps_access_granted_by_the_project(self, setup, db_session):
        _, group, user, fake = setup
        db_session.add_all([
            _membership(GitLabGroupMember, user, 40, gitlab_group_id=GROUP_ID),
            _membership(AppMember, user, 40, gitlab_project_id=PROJECT_ID),
        ])
        await db_session.commit()

        with patch("backend.services.gitlab_sync_service.asyncio.to_thread", new=_fake_to_thread):
            await _sync_group(db_session, _gl_with(group_members=[_gl_member(30)]), group)

        assert _console_accounts(fake, user)


class TestProjectSync:
    async def test_project_downgrade_below_maintainer_revokes(self, setup, db_session):
        app, _, user, fake = setup
        db_session.add(_membership(AppMember, user, 40, gitlab_project_id=PROJECT_ID))
        await db_session.commit()

        with patch("backend.services.gitlab_sync_service.asyncio.to_thread", new=_fake_to_thread):
            await _sync_project(db_session, _gl_with(project_members=[_gl_member(30)]), app)

        assert _console_accounts(fake, user) == []

    async def test_project_downgrade_keeps_access_granted_by_the_group(self, setup, db_session):
        app, _, user, fake = setup
        db_session.add_all([
            _membership(AppMember, user, 40, gitlab_project_id=PROJECT_ID),
            _membership(GitLabGroupMember, user, 40, gitlab_group_id=GROUP_ID),
        ])
        await db_session.commit()

        with patch("backend.services.gitlab_sync_service.asyncio.to_thread", new=_fake_to_thread):
            await _sync_project(db_session, _gl_with(project_members=[_gl_member(30)]), app)

        assert _console_accounts(fake, user)

    async def test_leaving_the_project_keeps_access_granted_by_the_group(self, setup, db_session):
        app, _, user, fake = setup
        db_session.add_all([
            _membership(AppMember, user, 40, gitlab_project_id=PROJECT_ID),
            _membership(GitLabGroupMember, user, 50, gitlab_group_id=GROUP_ID),
        ])
        await db_session.commit()

        with patch("backend.services.gitlab_sync_service.asyncio.to_thread", new=_fake_to_thread):
            await _sync_project(db_session, _gl_with(project_members=[]), app)

        assert _console_accounts(fake, user)


class TestAddMember:
    async def test_downgrade_through_add_member_revokes(self, setup, db_session):
        app, _, user, fake = setup
        db_session.add(_membership(AppMember, user, 40, gitlab_project_id=PROJECT_ID))
        await db_session.commit()

        with patch("backend.services.app_service._get_bot_client", return_value=MagicMock()):
            await AppService(db_session).add_member(app.id, GITLAB_USER_ID, 30)

        assert _console_accounts(fake, user) == []

    async def test_downgrade_through_add_member_keeps_access_granted_by_the_group(self, setup, db_session):
        app, _, user, fake = setup
        db_session.add_all([
            _membership(AppMember, user, 40, gitlab_project_id=PROJECT_ID),
            _membership(GitLabGroupMember, user, 40, gitlab_group_id=GROUP_ID),
        ])
        await db_session.commit()

        with patch("backend.services.app_service._get_bot_client", return_value=MagicMock()):
            await AppService(db_session).add_member(app.id, GITLAB_USER_ID, 30)

        assert _console_accounts(fake, user)


class TestUserDeactivation:
    async def test_deactivating_a_user_revokes_their_console_accounts(
        self, setup, client, admin_token
    ):
        _, _, user, fake = setup
        resp = await client.patch(
            f"/api/v1/users/{user.id}", json={"is_active": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False
        assert _console_accounts(fake, user) == []

    async def test_other_user_updates_do_not_touch_keycloak(self, setup, client, admin_token):
        _, _, user, fake = setup
        before = len(fake.requests)
        resp = await client.patch(
            f"/api/v1/users/{user.id}", json={"role": "dev"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert len(fake.requests) == before
        assert _console_accounts(fake, user)


class TestBestEffort:
    async def test_no_keycloak_call_while_keycloak_is_off_for_the_app(self, setup, db_session):
        app, group, user, fake = setup
        app.auth_enabled = False
        db_session.add_all([
            _membership(GitLabGroupMember, user, 40, gitlab_group_id=GROUP_ID),
            _membership(AppMember, user, 40, gitlab_project_id=PROJECT_ID),
        ])
        await db_session.commit()
        before = len(fake.requests)

        with patch("backend.services.gitlab_sync_service.asyncio.to_thread", new=_fake_to_thread):
            await _sync_group(db_session, _gl_with(group_members=[]), group)
            await _sync_project(db_session, _gl_with(project_members=[]), app)
        with patch("backend.services.app_service._get_bot_client", return_value=MagicMock()):
            await AppService(db_session).add_member(app.id, GITLAB_USER_ID, 30)

        assert len(fake.requests) == before

    async def test_keycloak_failure_never_breaks_the_sync(self, setup, db_session, monkeypatch):
        app, group, user, _ = setup
        db_session.add_all([
            _membership(GitLabGroupMember, user, 40, gitlab_group_id=GROUP_ID),
            _membership(AppMember, user, 40, gitlab_project_id=PROJECT_ID),
        ])
        await db_session.commit()

        def refuse(request):
            raise httpx.ConnectError("refused", request=request)

        monkeypatch.setattr(
            KeycloakService, "_client",
            lambda self, connection: KeycloakClient(
                connection.admin_url, connection.client_id, connection.client_secret,
                transport=httpx.MockTransport(refuse),
            ),
        )
        with patch("backend.services.gitlab_sync_service.asyncio.to_thread", new=_fake_to_thread):
            group_stats = await _sync_group(db_session, _gl_with(group_members=[]), group)
            project_stats = await _sync_project(db_session, _gl_with(project_members=[]), app)
        await db_session.commit()

        assert group_stats["revoked"] == 1
        assert project_stats["revoked"] == 1
