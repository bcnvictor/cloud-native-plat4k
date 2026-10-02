"""Local demo data for the Plat4k assistant (idempotent, never run in production).

Creates test accounts with different profiles, two fake groups (IDs 990001/990002,
unknown to GitLab so the sync worker leaves them alone) and a few applications.

Usage (repo root, containers running):
    docker compose exec -T backend python - < scripts/assistant-demo/seed.py

Accounts:
    admin@cnp.local      / admin      platform admin (role forced to ADMIN)
    maintainer@cnp.local / maintainer maintainer of Team Demo
    dev@cnp.local        / dev        developer of Team Demo
    viewer@cnp.local     / viewer     viewer of Team Demo, developer of Team Other
"""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.security import get_password_hash
from backend.db.models import (
    Application,
    ApplicationStatus,
    AppScaleState,
    Event,
    GitLabGroup,
    GitLabGroupMember,
    User,
)
from shared.models import MemberStatus, UserRole

USERS = [
    ("admin@cnp.local", "admin", UserRole.ADMIN),
    ("maintainer@cnp.local", "maintainer", UserRole.DEV),
    ("dev@cnp.local", "dev", UserRole.DEV),
    ("viewer@cnp.local", "viewer", UserRole.VIEWER),
]
GROUPS = [
    (990001, "Team Demo", "cnp-apps/team-demo"),
    (990002, "Team Other", "cnp-apps/team-other"),
]
# (group, email, GitLab access level) — 40 maintainer, 30 developer, 20 viewer
MEMBERS = [
    (990001, "maintainer@cnp.local", 40),
    (990001, "dev@cnp.local", 30),
    (990001, "viewer@cnp.local", 20),
    (990002, "viewer@cnp.local", 30),
]
# slug, group, status, last pipeline
APPS = [
    ("demo-api", 990001, ApplicationStatus.DEPLOYED, "success"),
    ("demo-web", 990001, ApplicationStatus.DEGRADED, "failed"),
    ("demo-worker", 990001, ApplicationStatus.ONBOARDING, None),
    ("other-secret", 990002, ApplicationStatus.DEPLOYED, "success"),
]


async def seed(db: AsyncSession) -> dict[str, int]:
    users: dict[str, User] = {}
    for email, password, role in USERS:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            user = User(email=email, hashed_password=get_password_hash(password), role=role)
            db.add(user)
        else:  # keep demo credentials/roles predictable
            user.hashed_password = get_password_hash(password)
            user.role = role
            user.is_active = True
        users[email] = user

    for gid, name, path in GROUPS:
        if await db.get(GitLabGroup, gid) is None:
            db.add(GitLabGroup(gitlab_group_id=gid, name=name, full_path=path))
    await db.commit()

    for gid, email, level in MEMBERS:
        uid = users[email].id
        member = (
            await db.execute(
                select(GitLabGroupMember).where(
                    GitLabGroupMember.gitlab_group_id == gid,
                    GitLabGroupMember.cnp_user_id == uid,
                )
            )
        ).scalar_one_or_none()
        if member is None:
            db.add(GitLabGroupMember(
                gitlab_group_id=gid, username=email.split("@")[0], access_level=level,
                cnp_user_id=uid, status=MemberStatus.ACTIVE,
            ))
        else:
            member.access_level = level
            member.status = MemberStatus.ACTIVE

    apps: dict[str, Application] = {}
    for slug, gid, status, pipeline in APPS:
        app = (await db.execute(select(Application).where(Application.slug == slug))).scalar_one_or_none()
        if app is None:
            app = Application(
                name=slug, slug=slug, owner="demo", owning_gitlab_group_id=gid,
                description=f"Application de démo ({slug})", framework="fastapi", origin="scaffold",
            )
            db.add(app)
        app.last_known_status = status
        app.last_pipeline_status = pipeline
        apps[slug] = app
    await db.commit()

    web = apps["demo-web"]
    events = [
        ("demo-seed-api-deployed", "app.deployed", "info", apps["demo-api"].id, {"env": "prod"}),
        ("demo-seed-web-degraded", "app.health.degraded", "critical", web.id,
         {"health": "Degraded", "env": "prod"}),
        ("demo-seed-web-stopped", "app.scale.stopped", "info", web.id, {"env": "dev"}),
    ]
    for key, typ, severity, app_id, payload in events:
        if (await db.execute(select(Event).where(Event.dedup_key == key))).first() is None:
            db.add(Event(type=typ, severity=severity, source="demo", app_id=app_id,
                         payload=payload, dedup_key=key))
    if (await db.execute(select(AppScaleState).where(AppScaleState.app_id == web.id))).first() is None:
        db.add(AppScaleState(app_id=web.id, env="dev", is_stopped=True))
    await db.commit()
    return {slug: a.id for slug, a in apps.items()}


async def main() -> None:
    from backend.core.config import settings

    engine = create_async_engine(settings.async_database_uri)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        ids = await seed(db)
    await engine.dispose()
    print("Demo accounts: admin@cnp.local/admin · maintainer@cnp.local/maintainer · "
          "dev@cnp.local/dev · viewer@cnp.local/viewer")
    print("Demo app ids:", ids)


if __name__ == "__main__":
    asyncio.run(main())
