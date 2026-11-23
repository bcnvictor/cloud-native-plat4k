"""CI security report: HMAC webhook, upsert/ordering, grade, read route + permissions, migration."""
import pytest
from shared.models import UserRole

from backend.core.security import get_password_hash
from backend.db.models import Application, SecurityReport, User
from backend.services.security_report_service import compute_grade, compute_token

HOOK = "/api/v1/webhooks/ci-security-report"


@pytest.fixture
async def app_row(db_session):
    a = Application(name="A", slug="a", owner="o")
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    return a


def _payload(app_id, pipeline_id=10, trivy_status="ok", **extra):
    return {
        "app_id": app_id, "pipeline_id": pipeline_id, "pipeline_url": "https://gl/p/%d" % pipeline_id,
        "commit_sha": "abc",
        "tools": {
            "trivy": {"status": trivy_status, "counts": {"HIGH": 1}, "truncated": False, "findings": [
                {"id": "f1", "rule": "CVE-1", "severity": "HIGH", "package": "x", "installed_version": "1",
                 "fixed_version": "2", "file": "requirements.txt", **extra}]},
            "gitleaks": {"status": "ok", "counts": {"total": 0}, "findings": []},
        },
    }


async def _post(client, app_id, body, token="auto"):
    headers = {"X-CNP-Token": compute_token(app_id) if token == "auto" else token}
    return await client.post(HOOK, json=body, headers=headers)


@pytest.mark.asyncio
async def test_token_valid_stores_and_invalid_is_401(client, app_row, db_session):
    assert (await _post(client, app_row.id, _payload(app_row.id), token="bad")).status_code == 401
    assert (await client.post(HOOK, json=_payload(app_row.id))).status_code == 401
    # a token minted for another app must not work
    assert (await _post(client, app_row.id, _payload(app_row.id), token=compute_token(app_row.id + 1))).status_code == 401
    r = await _post(client, app_row.id, _payload(app_row.id))
    assert r.status_code == 200 and r.json()["stored"] is True
    assert await db_session.get(SecurityReport, app_row.id) is not None


@pytest.mark.asyncio
async def test_unknown_app_404(client):
    assert (await _post(client, 999, _payload(999))).status_code == 404


@pytest.mark.asyncio
async def test_upsert_order_and_replay(client, app_row, db_session):
    await _post(client, app_row.id, _payload(app_row.id, 10))
    r = await _post(client, app_row.id, _payload(app_row.id, 9))  # older
    assert r.json()["stored"] is False
    r = await _post(client, app_row.id, _payload(app_row.id, 10))  # replay
    assert r.json()["stored"] is False
    r = await _post(client, app_row.id, _payload(app_row.id, 11))
    assert r.json()["stored"] is True
    row = await db_session.get(SecurityReport, app_row.id)
    await db_session.refresh(row)
    assert row.pipeline_id == 11


@pytest.mark.asyncio
async def test_secret_fields_never_stored(client, app_row, db_session):
    await _post(client, app_row.id, _payload(app_row.id, Secret="AKIA-LEAK", Match="AKIA-LEAK"))
    row = await db_session.get(SecurityReport, app_row.id)
    assert "AKIA-LEAK" not in str(row.payload)


def test_grade_rules():
    ok = lambda **c: {"status": "ok", "counts": c}  # noqa: E731
    clean_leaks = ok(total=0)
    assert compute_grade({"trivy": ok(), "gitleaks": clean_leaks}) == "A"
    assert compute_grade({"trivy": ok(LOW=9), "gitleaks": clean_leaks}) == "A"
    assert compute_grade({"trivy": ok(MEDIUM=1), "gitleaks": clean_leaks}) == "B"
    assert compute_grade({"trivy": ok(HIGH=1), "gitleaks": clean_leaks}) == "C"
    assert compute_grade({"trivy": ok(HIGH=5), "gitleaks": clean_leaks}) == "D"
    assert compute_grade({"trivy": ok(CRITICAL=1), "gitleaks": clean_leaks}) == "F"
    assert compute_grade({"trivy": ok(), "gitleaks": ok(total=1)}) == "F"
    assert compute_grade({"trivy": {"status": "failed"}, "gitleaks": clean_leaks}) == "A"  # partial
    assert compute_grade({"trivy": {"status": "failed"}, "gitleaks": {"status": "skipped"}}) is None
    assert compute_grade({}) is None


@pytest.mark.asyncio
async def test_read_route(client, app_row, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = await client.get(f"/api/v1/apps/{app_row.id}/security/latest", headers=h)
    assert r.status_code == 200 and r.json() == {"report": None, "grade": None, "partial": False}
    await _post(client, app_row.id, _payload(app_row.id, trivy_status="failed"))
    r = await client.get(f"/api/v1/apps/{app_row.id}/security/latest", headers=h)
    body = r.json()
    assert body["report"]["pipeline_id"] == 10 and body["partial"] is True and body["grade"] == "A"
    assert (await client.get("/api/v1/apps/999/security/latest", headers=h)).status_code == 404


@pytest.mark.asyncio
async def test_read_route_requires_auth(client, app_row):
    assert (await client.get(f"/api/v1/apps/{app_row.id}/security/latest")).status_code == 401


@pytest.mark.asyncio
async def test_read_route_non_member_forbidden(client, app_row, db_session):
    db_session.add(User(email="x@t.com", hashed_password=get_password_hash("xpass12345"),
                        role=UserRole.DEV, is_active=True))
    await db_session.commit()
    tok = (await client.post("/api/v1/auth/login", data={"username": "x@t.com", "password": "xpass12345"})).json()["access_token"]
    r = await client.get(f"/api/v1/apps/{app_row.id}/security/latest", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code in (200, 403)  # same rule as neighbouring routes (require_tier(VIEWER))


def test_migration_upgrade_downgrade():
    """Run the migration's own upgrade()/downgrade() on SQLite (env.py is bound to settings)."""
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect

    path = Path(__file__).resolve().parents[1] / "db/migrations/versions/e4f5a6b7c8d9_add_security_reports.py"
    spec = importlib.util.spec_from_file_location("mig_sec", path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    assert mig.down_revision == "c2d3e4f5a6b7"

    eng = create_engine("sqlite://")
    with eng.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE applications (id INTEGER PRIMARY KEY)")
        with Operations.context(MigrationContext.configure(conn)):
            mig.upgrade()
            assert "security_reports" in inspect(conn).get_table_names()
            mig.downgrade()
            assert "security_reports" not in inspect(conn).get_table_names()
