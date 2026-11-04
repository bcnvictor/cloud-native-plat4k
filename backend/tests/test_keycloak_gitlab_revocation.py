"""Console access follows the effective tier (4K-15/ADR-0027 §5).

A CNP user keeps a Keycloak console account only while their effective
tier on the app — best of project and owning-group membership, as in
tier_service.get_effective_tier — is Maintainer or above. Exercised through the real
triggers: GitLab sync (full and per user), AppService.add_member, deactivating the
CNP user and demoting an admin. Revocations run after the triggering change is
committed, never inside its transaction. Always best-effort: no Keycloak call while
Keycloak is off for the app, and a Keycloak failure never breaks the caller.
"""
from unittest.mock import MagicMock, patch

import httpx
import pytest
from shared.models import MemberStatus, UserRole
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.core.security import get_password_hash
from backend.db.models import AppMember, GitLabGroup, GitLabGroupMember, User
from backend.keycloak.client import KeycloakClient
from backend.services.app_service import AppService
from backend.services.gitlab_sync_service import (
    _sync_group,
    run_gitlab_sync,
    run_gitlab_sync_for_user,
)
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


async def _full_sync(db, *, group_members=(), project_members=()):
    gl = _gl_with(group_members=list(group_members), project_members=list(project_members))
    with patch("backend.services.gitlab_sync_service._build_gitlab_client", return_value=gl), \
            patch("backend.services.gitlab_sync_service.asyncio.to_thread", new=_fake_to_thread):
        return await run_gitlab_sync(db)


def _record_order(db, fake, monkeypatch) -> list[str]:
    """Commits of `db` and Keycloak requests, in the order they happen."""
    events: list[str] = []
    commit = db.commit

    async def recording_commit():
        events.append("commit")
        await commit()

    monkeypatch.setattr(db, "commit", recording_commit)
    handler = fake.handler

    def recording_handler(request):
        events.append("keycloak")
        return handler(request)

    fake.handler = recording_handler
    return events


class TestGroupSync:
    async def test_group_downgrade_below_maintainer_revokes(self, setup, db_session):
        _, group, user, fake = setup
        db_session.add(_membership(GitLabGroupMember, user, 40, gitlab_group_id=GROUP_ID))
        await db_session.commit()

        await _full_sync(db_session, group_members=[_gl_member(30)])

        assert _console_accounts(fake, user) == []

    async def test_leaving_the_group_revokes(self, setup, db_session):
        _, group, user, fake = setup
        db_session.add(_membership(GitLabGroupMember, user, 50, gitlab_group_id=GROUP_ID))
        await db_session.commit()

        await _full_sync(db_session, group_members=[])

        assert _console_accounts(fake, user) == []

    async def test_group_downgrade_revokes_with_production_session_settings(self, setup, db_session):
        """AsyncSessionLocal has autoflush=False: the revocation reads the committed
        membership change."""
        _, group, user, fake = setup
        db_session.add(_membership(GitLabGroupMember, user, 40, gitlab_group_id=GROUP_ID))
        await db_session.commit()
        db_session.sync_session.autoflush = False

        await _full_sync(db_session, group_members=[_gl_member(30)])

        assert _console_accounts(fake, user) == []

    async def test_group_downgrade_keeps_access_granted_by_the_project(self, setup, db_session):
        _, group, user, fake = setup
        db_session.add_all([
            _membership(GitLabGroupMember, user, 40, gitlab_group_id=GROUP_ID),
            _membership(AppMember, user, 40, gitlab_project_id=PROJECT_ID),
        ])
        await db_session.commit()

        await _full_sync(db_session, group_members=[_gl_member(30)], project_members=[_gl_member(40)])

        assert _console_accounts(fake, user)

    async def test_the_sync_itself_never_calls_keycloak(self, setup, db_session):
        """N6: the membership pass only collects what to revoke; Keycloak is called
        once the caller has committed."""
        app, group, user, fake = setup
        db_session.add(_membership(GitLabGroupMember, user, 40, gitlab_group_id=GROUP_ID))
        await db_session.commit()
        before = len(fake.requests)
        lost: set[tuple[int, int]] = set()

        with patch("backend.services.gitlab_sync_service.asyncio.to_thread", new=_fake_to_thread):
            await _sync_group(db_session, _gl_with(group_members=[]), group, lost_console_access=lost)

        assert len(fake.requests) == before
        assert lost == {(app.id, user.id)}

    async def test_revocation_runs_after_the_sync_commits(self, setup, db_session, monkeypatch):
        _, group, user, fake = setup
        db_session.add(_membership(GitLabGroupMember, user, 40, gitlab_group_id=GROUP_ID))
        await db_session.commit()
        events = _record_order(db_session, fake, monkeypatch)

        await _full_sync(db_session, group_members=[])

        assert _console_accounts(fake, user) == []
        assert "keycloak" in events
        assert events.index("commit") < events.index("keycloak")


class TestProjectSync:
    async def test_project_downgrade_below_maintainer_revokes(self, setup, db_session):
        _, _, user, fake = setup
        db_session.add(_membership(AppMember, user, 40, gitlab_project_id=PROJECT_ID))
        await db_session.commit()

        await _full_sync(db_session, project_members=[_gl_member(30)])

        assert _console_accounts(fake, user) == []

    async def test_project_downgrade_keeps_access_granted_by_the_group(self, setup, db_session):
        _, _, user, fake = setup
        db_session.add_all([
            _membership(AppMember, user, 40, gitlab_project_id=PROJECT_ID),
            _membership(GitLabGroupMember, user, 40, gitlab_group_id=GROUP_ID),
        ])
        await db_session.commit()

        await _full_sync(db_session, group_members=[_gl_member(40)], project_members=[_gl_member(30)])

        assert _console_accounts(fake, user)

    async def test_leaving_the_project_keeps_access_granted_by_the_group(self, setup, db_session):
        _, _, user, fake = setup
        db_session.add_all([
            _membership(AppMember, user, 40, gitlab_project_id=PROJECT_ID),
            _membership(GitLabGroupMember, user, 50, gitlab_group_id=GROUP_ID),
        ])
        await db_session.commit()

        await _full_sync(db_session, group_members=[_gl_member(50)], project_members=[])

        assert _console_accounts(fake, user)

    async def test_user_sync_revokes_after_it_commits(self, setup, db_session, monkeypatch):
        """run_gitlab_sync_for_user (login, "sync my teams") follows the same rule."""
        _, _, user, fake = setup
        db_session.add(_membership(AppMember, user, 40, gitlab_project_id=PROJECT_ID))
        await db_session.commit()
        events = _record_order(db_session, fake, monkeypatch)
        gl = _gl_with(project_members=[_gl_member(30)])
        gl.groups.list.return_value = []

        with patch("backend.services.gitlab_sync_service._build_gitlab_client", return_value=gl), \
                patch("backend.services.gitlab_sync_service.asyncio.to_thread", new=_fake_to_thread):
            await run_gitlab_sync_for_user(db_session, user.id)

        assert _console_accounts(fake, user) == []
        assert "keycloak" in events
        assert events.index("commit") < events.index("keycloak")


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


@pytest.fixture
def background_sessions(db_session, monkeypatch):
    """Background revocations open their own session (the request's is closed by
    then); point it at the test database."""
    import backend.services.keycloak_service as keycloak_service

    monkeypatch.setattr(
        keycloak_service, "AsyncSessionLocal",
        async_sessionmaker(bind=db_session.bind, expire_on_commit=False),
    )


class TestUserUpdates:
    async def test_deactivating_a_user_revokes_their_console_accounts(
        self, setup, client, admin_token, background_sessions
    ):
        _, _, user, fake = setup
        resp = await client.patch(
            f"/api/v1/users/{user.id}", json={"is_active": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False
        assert _console_accounts(fake, user) == []

    async def test_deactivation_revokes_after_the_commit(
        self, setup, client, admin_token, background_sessions, db_session, monkeypatch
    ):
        _, _, user, fake = setup
        events = _record_order(db_session, fake, monkeypatch)
        resp = await client.patch(
            f"/api/v1/users/{user.id}", json={"is_active": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert "keycloak" in events
        assert events.index("commit") < events.index("keycloak")

    async def test_demoting_an_admin_revokes_console_access_they_no_longer_have(
        self, setup, client, admin_token, background_sessions, db_session
    ):
        """N4: an admin gets console access on any app (tier bypass). Demoted, they
        keep it only where their own membership grants Maintainer+."""
        _, _, user, fake = setup
        user.role = UserRole.ADMIN
        await db_session.commit()
        resp = await client.patch(
            f"/api/v1/users/{user.id}", json={"role": "dev"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "dev"
        assert _console_accounts(fake, user) == []

    async def test_demoting_an_admin_keeps_access_granted_by_membership(
        self, setup, client, admin_token, background_sessions, db_session
    ):
        _, _, user, fake = setup
        user.role = UserRole.ADMIN
        db_session.add(_membership(GitLabGroupMember, user, 40, gitlab_group_id=GROUP_ID))
        await db_session.commit()
        resp = await client.patch(
            f"/api/v1/users/{user.id}", json={"role": "viewer"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert _console_accounts(fake, user)

    async def test_other_user_updates_do_not_touch_keycloak(
        self, setup, client, admin_token, background_sessions
    ):
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

        await _full_sync(db_session)
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
        total = await _full_sync(db_session)

        assert total["groups"]["revoked"] == 1
        assert total["projects"]["revoked"] == 1
