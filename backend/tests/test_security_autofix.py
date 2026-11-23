"""Mode B (CNP AI autofix): fake provider + fake GitLab client, no network, no real project."""
import json

import httpx
import pytest
from sqlalchemy import select

from backend.ai.provider import LLMProvider, LLMResponse
from backend.api.routes import security as security_routes
from backend.core.config import settings
from backend.db.models import Application, AuditLog, SecurityReport
from backend.main import app as fastapi_app
from backend.services.security_autofix_service import AutofixError, resolve_target, validate_rewrite

REQ = "flask==1.0\nrequests==2.0\n"


class FakeProvider(LLMProvider):
    def __init__(self, content=None, exc=None):
        self.content, self.exc, self.calls = content, exc, []

    async def complete(self, messages, model, max_tokens=4096, temperature=0.3, tools=None):
        self.calls.append(messages)
        if self.exc:
            raise self.exc
        return LLMResponse(content=self.content, model="fake")

    def supports_streaming(self):
        return False


class FakeGL:
    def __init__(self, files=None, branch_exists=False):
        self.files = files or {"requirements.txt": REQ}
        self._branch_exists = branch_exists
        self.commits, self.mrs, self.read_paths = [], [], []

    def branch_exists(self, project, branch): return self._branch_exists
    def find_mr_url_for_branch(self, project, branch): return "https://gl/mr/existing"
    def get_default_branch(self, project): return "main"
    def read_file(self, project, path, ref="main"):
        self.read_paths.append(path)
        return self.files[path]
    def create_branch(self, project, branch, ref="main"): self.branch = branch
    def push_multiple_files(self, project, branch, msg, actions): self.commits.append((branch, msg, actions))
    def create_mr(self, project, src, dst, title, description="", labels=None):
        self.mrs.append({"title": title, "description": description, "labels": labels})
        return {"iid": 1, "web_url": "https://gl/mr/1"}


GOOD = json.dumps({"new_content": "flask==2.0.1\nrequests==2.0\n"})


def _finding(**kw):
    f = {"id": "dep1", "rule": "CVE-2024-1", "severity": "HIGH", "title": "t", "package": "flask",
         "installed_version": "1.0", "fixed_version": "2.0.1", "file": "requirements.txt"}
    f.update(kw)
    return f


@pytest.fixture
async def seeded(db_session):
    a = Application(name="Shop", slug="shop", owner="o", repo_url="https://gitlab.com/g/shop")
    db_session.add(a)
    await db_session.commit()
    db_session.add(SecurityReport(app_id=a.id, pipeline_id=1, pipeline_url="u", commit_sha="c", payload={
        "trivy": {"status": "ok", "counts": {"HIGH": 2}, "findings": [
            _finding(), _finding(id="nofix", fixed_version=None), _finding(id="lock", file="poetry.lock", package="flask"),
            _finding(id="ci", file=".gitlab-ci.yml"), _finding(id="trav", file="../etc/passwd")]},
        "gitleaks": {"status": "ok", "counts": {"total": 1}, "findings": [
            {"id": "leak", "rule": "aws", "severity": "CRITICAL", "file": "a.py", "line": 1}]}}))
    await db_session.commit()
    return a


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(settings, "AI_ASSISTANT_ENABLED", True)
    state = {"provider": FakeProvider(GOOD), "gl": FakeGL()}
    monkeypatch.setattr(security_routes, "get_provider", lambda *a, **k: state["provider"])
    fastapi_app.dependency_overrides[security_routes.get_autofix_gitlab_client] = lambda: state["gl"]
    yield state
    fastapi_app.dependency_overrides.pop(security_routes.get_autofix_gitlab_client, None)


def _url(app, fid="dep1"):
    return f"/api/v1/apps/{app.id}/security/findings/{fid}/autofix"


def _h(tok): return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_nominal_creates_draft_mr(client, seeded, setup, admin_token, db_session):
    r = await client.post(_url(seeded), headers=_h(admin_token))
    assert r.status_code == 200 and r.json() == {"status": "created", "mr_url": "https://gl/mr/1", "message": None}
    gl = setup["gl"]
    assert gl.read_paths == ["requirements.txt"]  # only the target manifest was read
    assert len(setup["provider"].calls) == 1  # exactly one LLM call
    branch, _, actions = gl.commits[0]
    assert branch == "cnp/autofix/dep1" and len(actions) == 1 and "flask==2.0.1" in actions[0]["content"]
    mr = gl.mrs[0]
    assert mr["title"].startswith("Draft: ") and mr["labels"] == ["cnp-autofix"]
    logs = (await db_session.execute(select(AuditLog).where(AuditLog.action == "SECURITY_AUTOFIX_MR"))).scalars().all()
    assert len(logs) == 1


@pytest.mark.asyncio
async def test_existing_branch_returns_existing_mr(client, seeded, setup, admin_token):
    setup["gl"] = FakeGL(branch_exists=True)
    r = await client.post(_url(seeded), headers=_h(admin_token))
    assert r.json()["status"] == "exists" and r.json()["mr_url"] == "https://gl/mr/existing"
    assert setup["provider"].calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [
    "not json",
    json.dumps({"new_content": "flask==1.0\nrequests==2.0\n"}),  # unchanged
    json.dumps({"new_content": "flask==2.0.1\nrequests==9.9\n"}),  # touches another package
    json.dumps({"new_content": "flask==2.0.1\nrequests==2.0\nevil-pkg==1\n"}),  # extra line
    json.dumps({"new_content": "flask==3.0\nrequests==2.0\n"}),  # wrong version
])
async def test_no_fix_when_invalid_or_out_of_scope(client, seeded, setup, admin_token, content):
    setup["provider"] = FakeProvider(content)
    r = await client.post(_url(seeded), headers=_h(admin_token))
    assert r.status_code == 200 and r.json()["status"] == "no_fix" and r.json()["message"]
    assert setup["gl"].commits == [] and setup["gl"].mrs == []


@pytest.mark.asyncio
@pytest.mark.parametrize("fid", ["nofix", "ci", "trav", "leak", "unknown"])
async def test_forbidden_or_unfixable_findings(client, seeded, setup, admin_token, fid):
    r = await client.post(_url(seeded, fid), headers=_h(admin_token))
    assert r.status_code in (404, 422)
    assert setup["provider"].calls == [] and setup["gl"].mrs == []


@pytest.mark.asyncio
async def test_lockfile_maps_to_manifest_with_warning(client, seeded, setup, admin_token):
    setup["gl"] = FakeGL(files={"pyproject.toml": 'flask = "1.0"\n'})
    setup["provider"] = FakeProvider(json.dumps({"new_content": 'flask = "2.0.1"\n'}))
    r = await client.post(_url(seeded, "lock"), headers=_h(admin_token))
    assert r.json()["status"] == "created"
    assert "lockfile was **not** regenerated" in setup["gl"].mrs[0]["description"]


@pytest.mark.asyncio
async def test_ai_disabled(client, seeded, setup, admin_token, monkeypatch):
    monkeypatch.setattr(settings, "AI_ASSISTANT_ENABLED", False)
    r = await client.post(_url(seeded), headers=_h(admin_token))
    assert r.status_code == 503 and setup["provider"].calls == []


@pytest.mark.asyncio
async def test_quota_and_provider_errors(client, seeded, setup, admin_token):
    resp = httpx.Response(429, request=httpx.Request("POST", "http://x"))
    setup["provider"] = FakeProvider(exc=httpx.HTTPStatusError("q", request=resp.request, response=resp))
    r = await client.post(_url(seeded), headers=_h(admin_token))
    assert r.status_code == 429 and "quota" in r.json()["detail"].lower()
    resp = httpx.Response(500, request=httpx.Request("POST", "http://x"))
    setup["provider"] = FakeProvider(exc=httpx.HTTPStatusError("e", request=resp.request, response=resp))
    assert (await client.post(_url(seeded), headers=_h(admin_token))).status_code == 502


@pytest.mark.asyncio
async def test_permissions(client, seeded, setup, dev_token):
    r = await client.post(_url(seeded), headers=_h(dev_token))  # no membership -> below developer
    assert r.status_code == 403
    assert (await client.post(_url(seeded))).status_code == 401
    assert setup["provider"].calls == []


@pytest.mark.asyncio
async def test_no_secret_reaches_llm_or_mr(client, seeded, setup, admin_token):
    secret = "glpat-abcdefghijklmnopqrstuvwx"
    setup["gl"] = FakeGL(files={"requirements.txt": REQ + f"# token {secret}\n"})
    setup["provider"] = FakeProvider(json.dumps({"new_content": "flask==2.0.1\nrequests==2.0\n"}))
    await client.post(_url(seeded), headers=_h(admin_token))
    sent = " ".join(m.content for m in setup["provider"].calls[0])
    assert secret not in sent and "[REDACTED:" in sent


def test_resolve_target_rules():
    assert resolve_target("requirements.txt").manifest == "requirements.txt"
    assert resolve_target("svc/package-lock.json").manifest == "svc/package.json"
    for bad in ("../x/requirements.txt", "/etc/passwd", ".gitlab-ci.yml", "Dockerfile", "a/.git/config", "app.py", None, "a b/requirements.txt"):
        with pytest.raises(AutofixError):
            resolve_target(bad)


def test_validate_rewrite_caps_diff():
    old = "\n".join(f"flask-{i}==1" for i in range(30))
    assert validate_rewrite(old, old.replace("==1", "==2.0.1"), "flask", "2.0.1") is not None  # too many lines
