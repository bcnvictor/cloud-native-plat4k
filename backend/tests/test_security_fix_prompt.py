"""Mode A fix-prompt: templates, secret safety, truncation, authorization, works with AI off."""
import pytest

from backend.db.models import Application, SecurityReport
from backend.services.security_fix_prompts import MAX_LISTED, build_fix_prompt

SECRET = "AKIAIOSFODNN7EXAMPLE"


def _dep(i=1, fixed="2.0.1"):
    return {"id": f"dep{i}", "rule": f"CVE-2024-{i:04d}", "severity": "HIGH", "title": "t", "package": "flask",
            "installed_version": "1.0", "fixed_version": fixed, "file": "requirements.txt"}


LEAK = {"id": "leak1", "rule": "aws-access-key", "severity": "CRITICAL", "title": "AWS", "file": "src/a.py", "line": 12}


def _report(trivy=None, leaks=None, tcount=None):
    payload = {
        "trivy": {"status": "ok", "counts": {"HIGH": tcount or len(trivy or [])}, "truncated": False, "findings": trivy or []},
        "gitleaks": {"status": "ok", "counts": {"total": len(leaks or [])}, "truncated": False, "findings": leaks or []},
    }
    return SecurityReport(app_id=1, pipeline_id=5, pipeline_url="https://gl/p/5", commit_sha="deadbeefcafe", payload=payload)


APP = Application(name="Shop", slug="shop", owner="o", repo_url="https://gitlab.com/g/shop")


def test_dependency_template():
    p = build_fix_prompt(APP, _report(trivy=[_dep()]), "dep1")
    for needle in ("Shop", "https://gitlab.com/g/shop", "https://gl/p/5", "CVE-2024-0001", "`flask`", "`1.0`",
                   "`2.0.1`", "requirements.txt", "tests and linter", ".gitlab-ci.yml", "`dep1`", "open a Merge Request"):
        assert needle in p, needle
    assert "WARNING" not in p


def test_dependency_without_fix():
    p = build_fix_prompt(APP, _report(trivy=[_dep(fixed=None)]), "dep1")
    assert "no fixed version" in p


def test_secret_template_warns_and_has_no_value():
    p = build_fix_prompt(APP, _report(leaks=[LEAK]), "leak1")
    assert p.startswith("> **WARNING")
    assert "revoked / rotated" in p and "src/a.py:12" in p and "environment variable" in p
    assert SECRET not in p


def test_all_truncates_long_lists():
    deps = [_dep(i) for i in range(1, 31)]
    p = build_fix_prompt(APP, _report(trivy=deps, tcount=120), "all")
    assert f"### Finding {MAX_LISTED}" in p and f"### Finding {MAX_LISTED + 1}" not in p
    assert f"and {120 - MAX_LISTED} other finding(s)" in p


def test_all_with_secret_has_warning():
    p = build_fix_prompt(APP, _report(trivy=[_dep()], leaks=[LEAK]), "all")
    assert "already compromised" in p


def test_unknown_or_empty():
    assert build_fix_prompt(APP, _report(trivy=[_dep()]), "nope") is None
    assert build_fix_prompt(APP, _report(), "all") is None


def test_redaction_applied():
    d = _dep()
    d["file"] = "glpat-abcdefghijklmnopqrstu.txt"
    assert "glpat-abcdefghijklmnopqrstu" not in build_fix_prompt(APP, _report(trivy=[d]), "dep1")


@pytest.fixture
async def seeded(db_session):
    a = Application(name="Shop", slug="shop2", owner="o", repo_url="https://gitlab.com/g/shop2")
    db_session.add(a)
    await db_session.commit()
    db_session.add(SecurityReport(app_id=a.id, pipeline_id=5, pipeline_url="https://gl/p/5", commit_sha="deadbeef",
                                  payload=_report(trivy=[_dep()], leaks=[LEAK]).payload))
    await db_session.commit()
    return a


@pytest.mark.asyncio
async def test_route_works_with_ai_off_and_auth(client, seeded, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    url = f"/api/v1/apps/{seeded.id}/security/fix-prompt"
    r = await client.get(url, params={"finding": "dep1"}, headers=h)  # AI_PROVIDER=mock / assistant disabled in tests
    assert r.status_code == 200 and "CVE-2024-0001" in r.json()["prompt"]
    assert (await client.get(url, params={"finding": "all"}, headers=h)).status_code == 200
    assert (await client.get(url, params={"finding": "zzz"}, headers=h)).status_code == 404
    assert (await client.get(url, params={"finding": "dep1"})).status_code == 401
