"""CI SBOM inventory: HMAC webhook (gzip), ordering/replay, transactional replace, bounds, admin search, migration."""
import gzip
import json

import pytest
from shared.models import UserRole
from sqlalchemy import func, select

from backend.core.security import get_password_hash
from backend.db.models import Application, GitLabGroup, SbomComponent, SbomSnapshot, User
from backend.services.security_report_service import compute_token

HOOK = "/api/v1/webhooks/ci-sbom"
SEARCH = "/api/v1/admin/dependencies"


@pytest.fixture
async def app_row(db_session):
    a = Application(name="Shop", slug="shop", owner="o")
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    return a


def _comp(name="lodash", version="4.17.20", eco="npm", direct=True, licenses=("MIT",)):
    return {"purl": f"pkg:{eco}/{name}@{version}", "name": name, "version": version, "ecosystem": eco,
            "direct": direct, "licenses": list(licenses)}


def _payload(app_id, pipeline_id=10, components=None, truncated=False, **extra):
    return {"app_id": app_id, "pipeline_id": pipeline_id, "commit_sha": "abc",
            "components": components if components is not None else [_comp(), _comp("express", "4.18.0", direct=False)],
            "truncated": truncated, **extra}


async def _post(client, app_id, body, token="auto", gz=True, raw=None):
    headers = {"X-CNP-Token": compute_token(app_id) if token == "auto" else token,
               "Content-Type": "application/json"}
    data = raw if raw is not None else json.dumps(body).encode()
    if gz:
        data = gzip.compress(data) if raw is None else data
        headers["Content-Encoding"] = "gzip"
    return await client.post(HOOK, content=data, headers=headers)


async def _count(db, app_id):
    return (await db.execute(select(func.count()).select_from(SbomComponent)
                             .where(SbomComponent.app_id == app_id))).scalar_one()


@pytest.mark.asyncio
async def test_token_valid_stores_and_invalid_is_401(client, app_row, db_session):
    assert (await _post(client, app_row.id, _payload(app_row.id), token="bad")).status_code == 401
    r = await client.post(HOOK, content=gzip.compress(b"{}"), headers={"Content-Encoding": "gzip"})
    assert r.status_code == 422  # no app_id: nothing to authenticate against
    no_tok = await client.post(HOOK, content=json.dumps(_payload(app_row.id)))
    assert no_tok.status_code == 401
    other = compute_token(app_row.id + 1)  # token minted for another app
    assert (await _post(client, app_row.id, _payload(app_row.id), token=other)).status_code == 401
    assert await _count(db_session, app_row.id) == 0
    r = await _post(client, app_row.id, _payload(app_row.id))
    assert r.status_code == 200 and r.json()["stored"] is True
    snap = await db_session.get(SbomSnapshot, app_row.id)
    assert snap.component_count == 2 and snap.truncated is False and snap.pipeline_id == 10


@pytest.mark.asyncio
async def test_plain_json_also_accepted(client, app_row):
    r = await _post(client, app_row.id, _payload(app_row.id), gz=False)
    assert r.status_code == 200 and r.json()["stored"] is True


@pytest.mark.asyncio
async def test_unknown_app_404_and_bad_gzip_400(client):
    assert (await _post(client, 999, _payload(999))).status_code == 404
    r = await _post(client, 1, None, raw=b"not gzip")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_order_replay_and_transactional_replace(client, app_row, db_session):
    await _post(client, app_row.id, _payload(app_row.id, 10))
    assert (await _post(client, app_row.id, _payload(app_row.id, 9, [_comp("old")]))).json()["stored"] is False
    assert (await _post(client, app_row.id, _payload(app_row.id, 10, [_comp("old")]))).json()["stored"] is False
    assert await _count(db_session, app_row.id) == 2  # untouched by ignored posts
    r = await _post(client, app_row.id, _payload(app_row.id, 11, [_comp("only-new", "1.0.0")]))
    assert r.json()["stored"] is True
    names = (await db_session.execute(select(SbomComponent.name).where(SbomComponent.app_id == app_row.id))).scalars().all()
    assert names == ["only-new"]  # previous components gone
    snap = await db_session.get(SbomSnapshot, app_row.id)
    await db_session.refresh(snap)
    assert snap.pipeline_id == 11 and snap.component_count == 1


@pytest.mark.asyncio
async def test_truncated_flag_stored_and_duplicates_collapsed(client, app_row, db_session):
    comps = [_comp(), _comp()]  # same purl+version twice
    await _post(client, app_row.id, _payload(app_row.id, components=comps, truncated=True))
    snap = await db_session.get(SbomSnapshot, app_row.id)
    assert snap.truncated is True and snap.component_count == 1


@pytest.mark.asyncio
async def test_unknown_fields_are_dropped(client, app_row, db_session):
    c = _comp()
    c["secret"] = "AKIA-LEAK"
    await _post(client, app_row.id, _payload(app_row.id, components=[c], password="x"))
    rows = (await db_session.execute(select(SbomComponent))).scalars().all()
    assert "AKIA-LEAK" not in str([vars(r) for r in rows])


@pytest.mark.asyncio
async def test_payload_bounds(client, app_row):
    aid = app_row.id
    assert (await _post(client, aid, _payload(aid, components=[_comp()] * 5001))).status_code == 422
    assert (await _post(client, aid, _payload(aid, components=[_comp(name="x" * 201)]))).status_code == 422
    assert (await _post(client, aid, _payload(aid, components=[_comp(version="")]))).status_code == 422
    assert (await _post(client, aid, _payload(aid, components=[_comp(eco="Bad Eco!")]))).status_code == 422
    assert (await _post(client, aid, _payload(aid, components=[_comp(licenses=["MIT"] * 11)]))).status_code == 422
    assert (await _post(client, aid, _payload(aid, pipeline_id=10**20))).status_code == 422
    big = _payload(aid)
    big["commit_sha"] = "a" * 65
    assert (await _post(client, aid, big)).status_code == 422
    assert (await _post(client, aid, _payload(aid, components=[_comp()] * 5000))).status_code == 200


@pytest.mark.asyncio
async def test_decompression_bomb_rejected(client, app_row):
    bomb = gzip.compress(b" " * (9 * 1024 * 1024))  # tiny on the wire, > 8 MB once decompressed
    r = await client.post(HOOK, content=bomb, headers={"Content-Encoding": "gzip",
                                                        "X-CNP-Token": compute_token(app_row.id)})
    assert r.status_code == 413
    r = await client.post(HOOK, content=b"x" * (2 * 1024 * 1024 + 1), headers={"X-CNP-Token": compute_token(app_row.id)})
    assert r.status_code == 413


# ── admin search ──────────────────────────────────────────────────────────────


@pytest.fixture
async def two_apps(client, app_row, db_session):
    db_session.add(GitLabGroup(gitlab_group_id=7, name="Team Pay", full_path="pay"))
    other = Application(name="Billing", slug="billing", owner="o", owning_gitlab_group_id=7)
    idle = Application(name="Idle", slug="idle", owner="o")  # no SBOM yet
    db_session.add_all([other, idle])
    await db_session.commit()
    await _post(client, app_row.id, _payload(app_row.id, 5, [
        _comp("Lodash", "4.17.20"), _comp("express", "4.18.0", direct=False),
        _comp("my_pkg%", "1.0.0", eco="pypi", direct=None, licenses=())]))
    await _post(client, other.id, _payload(other.id, 6, [_comp("lodash", "4.17.21"), _comp("django", "4.2", eco="pypi")]))
    return app_row, other, idle


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_search_case_version_ecosystem_and_fields(client, two_apps, admin_token):
    r = (await client.get(SEARCH, params={"q": "LODASH"}, headers=_h(admin_token))).json()
    assert r["total"] == 2
    by_app = {i["app_name"]: i for i in r["items"]}
    assert by_app["Billing"]["group"] == "Team Pay" and by_app["Shop"]["group"] is None
    assert (by_app["Billing"]["group_slug"], by_app["Billing"]["app_slug"]) == ("pay", "billing")
    assert by_app["Shop"]["group_slug"] is None
    assert by_app["Shop"]["direct"] is True and by_app["Shop"]["licenses"] == ["MIT"]
    r = (await client.get(SEARCH, params={"q": "lodash", "version": "4.17.21"}, headers=_h(admin_token))).json()
    assert [i["app_name"] for i in r["items"]] == ["Billing"]
    r = (await client.get(SEARCH, params={"ecosystem": "pypi"}, headers=_h(admin_token))).json()
    assert {i["package"] for i in r["items"]} == {"my_pkg%", "django"}
    assert next(i for i in r["items"] if i["package"] == "my_pkg%")["direct"] is None


@pytest.mark.asyncio
async def test_search_wildcards_are_literal(client, two_apps, admin_token):
    h = _h(admin_token)
    assert (await client.get(SEARCH, params={"q": "%"}, headers=h)).json()["total"] == 1  # only "my_pkg%"
    assert (await client.get(SEARCH, params={"q": "_"}, headers=h)).json()["total"] == 1
    assert (await client.get(SEARCH, params={"q": "x' OR 1=1 --"}, headers=h)).json()["total"] == 0


@pytest.mark.asyncio
async def test_search_pagination_and_limit_cap(client, two_apps, admin_token):
    h = _h(admin_token)
    p1 = (await client.get(SEARCH, params={"limit": 2, "offset": 0}, headers=h)).json()
    p2 = (await client.get(SEARCH, params={"limit": 2, "offset": 2}, headers=h)).json()
    assert p1["total"] == 5 and len(p1["items"]) == 2 and len(p2["items"]) == 2
    assert not {(i["app_id"], i["package"]) for i in p1["items"]} & {(i["app_id"], i["package"]) for i in p2["items"]}
    assert (await client.get(SEARCH, params={"limit": 201}, headers=h)).status_code == 422


@pytest.mark.asyncio
async def test_search_coverage(client, two_apps, admin_token):
    cov = (await client.get(SEARCH, params={"q": "nomatch"}, headers=_h(admin_token))).json()["coverage"]
    assert cov["apps_total"] == 3 and cov["apps_with_sbom"] == 2
    assert cov["oldest_snapshot"] and cov["newest_snapshot"] and cov["oldest_snapshot"] <= cov["newest_snapshot"]


@pytest.mark.asyncio
async def test_search_requires_admin(client, two_apps, db_session, dev_token):
    assert (await client.get(SEARCH)).status_code == 401
    assert (await client.get(SEARCH, headers=_h(dev_token))).status_code == 403
    db_session.add(User(email="v@t.com", hashed_password=get_password_hash("vpass12345"),
                        role=UserRole.VIEWER, is_active=True))
    await db_session.commit()
    tok = (await client.post("/api/v1/auth/login", data={"username": "v@t.com", "password": "vpass12345"})).json()["access_token"]
    assert (await client.get(SEARCH, headers=_h(tok))).status_code == 403


@pytest.mark.asyncio
async def test_app_deletion_cascades(client, two_apps, db_session):
    app, _, _ = two_apps
    await db_session.execute(Application.__table__.delete().where(Application.id == app.id))
    await db_session.commit()
    # sqlite test DB does not enforce FKs by default: the cascade itself is declared on the FK.
    fks = {fk.ondelete for fk in SbomComponent.__table__.foreign_keys} | {fk.ondelete for fk in SbomSnapshot.__table__.foreign_keys}
    assert fks == {"CASCADE"}


def test_migration_upgrade_downgrade():
    """Run the migration's own upgrade()/downgrade() on SQLite (env.py is bound to settings)."""
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect

    path = Path(__file__).resolve().parents[1] / "db/migrations/versions/f5a6b7c8d9e0_add_sbom_inventory.py"
    spec = importlib.util.spec_from_file_location("mig_sbom", path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    assert mig.down_revision == "e4f5a6b7c8d9"

    eng = create_engine("sqlite://")
    with eng.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE applications (id INTEGER PRIMARY KEY)")
        with Operations.context(MigrationContext.configure(conn)):
            mig.upgrade()
            insp = inspect(conn)
            assert {"sbom_snapshots", "sbom_components"} <= set(insp.get_table_names())
            # SQLAlchemy cannot reflect the expression index lower(name): read sqlite_master directly.
            idx = {r[0] for r in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='sbom_components'")}
            assert {"ix_sbom_components_lower_name", "ix_sbom_components_ecosystem_name"} <= idx
            mig.downgrade()
            assert not {"sbom_snapshots", "sbom_components"} & set(inspect(conn).get_table_names())


# ── search by CVE (OSV.dev mocked) ────────────────────────────────────────────

import httpx  # noqa: E402

from backend.services import sbom_service  # noqa: E402

BYCVE = "/api/v1/admin/dependencies/by-cve"
LOG4J_CVE = {"id": "CVE-2021-44228", "summary": "Log4Shell", "aliases": ["GHSA-jfh8-c2jp-5v3q"],
             "related": ["SUSE-SU-2021:4096-1"],
             # like the real CVE record: GIT ranges only, no package
             "affected": [{"ranges": [{"type": "GIT", "events": [{"introduced": "0"}, {"fixed": "abc"}]}],
                           "versions": ["2.14.1"]}]}
LOG4J_GHSA = {"id": "GHSA-jfh8-c2jp-5v3q", "affected": [
    {"package": {"ecosystem": "Maven", "name": "org.apache.logging.log4j:log4j-core"},
     "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "2.0-beta9"}, {"fixed": "2.15.0"}]}],
     "versions": ["2.14.1", "2.14.0"]},
    {"package": {"ecosystem": "Debian:11", "name": "apache-log4j2"}, "versions": ["2.14.1"]},  # out of scope
]}
RANGE_ONLY = {"id": "CVE-2023-1111", "aliases": [], "affected": [
    {"package": {"ecosystem": "npm", "name": "lodash"},
     "ranges": [{"type": "SEMVER", "events": [{"introduced": "0"}, {"fixed": "4.17.21"}]}]}]}


@pytest.fixture
def osv(monkeypatch):
    """Mock OSV.dev with an httpx MockTransport; records every outgoing request."""
    sbom_service._osv_cache.clear()
    db: dict = {"CVE-2021-44228": LOG4J_CVE, "GHSA-jfh8-c2jp-5v3q": LOG4J_GHSA, "CVE-2023-1111": RANGE_ONLY}
    seen: list[httpx.Request] = []
    state = {"mode": "ok"}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if state["mode"] == "timeout":
            raise httpx.ReadTimeout("slow", request=request)
        if state["mode"] == "500":
            return httpx.Response(500)
        vid = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=db[vid]) if vid in db else httpx.Response(404, json={"code": 5})

    monkeypatch.setattr(sbom_service, "_osv_client", lambda: httpx.AsyncClient(
        base_url="https://osv.test", transport=httpx.MockTransport(handler)))
    return type("Osv", (), {"seen": seen, "state": state, "db": db})


@pytest.fixture
async def cve_apps(client, app_row, db_session):
    other = Application(name="Billing", slug="billing", owner="o")
    db_session.add(other)
    await db_session.commit()
    mv = lambda v: {"purl": f"pkg:maven/org.apache.logging.log4j/log4j-core@{v}", "name": "log4j-core",  # noqa: E731
                    "version": v, "ecosystem": "maven", "direct": True, "licenses": ["Apache-2.0"]}
    await _post(client, app_row.id, _payload(app_row.id, 1, [mv("2.14.1"), _comp("lodash", "4.17.20")]))
    await _post(client, other.id, _payload(other.id, 1, [mv("2.17.1"), _comp("lodash", "4.17.21")]))
    return app_row, other


@pytest.mark.asyncio
async def test_by_cve_explicit_versions_via_alias(client, cve_apps, osv, admin_token):
    r = await client.get(BYCVE, params={"id": "cve-2021-44228"}, headers=_h(admin_token))  # case-insensitive
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cve"] == "CVE-2021-44228" and body["aliases"] == ["GHSA-jfh8-c2jp-5v3q"] and body["partial"] is False
    assert len(body["packages"]) == 1  # Debian entry is outside the inventory ecosystems
    pkg = body["packages"][0]
    assert (pkg["ecosystem"], pkg["name"], pkg["mode"]) == ("Maven", "org.apache.logging.log4j:log4j-core", "explicit")
    assert [(m["app_name"], m["version"]) for m in pkg["matches"]] == [("Shop", "2.14.1")]  # 2.17.1 not listed
    assert pkg["ranges"] == [">= 2.0-beta9, < 2.15.0"]
    assert body["coverage"]["apps_with_sbom"] == 2


@pytest.mark.asyncio
async def test_by_cve_ranges_only_lists_package_users_unevaluated(client, cve_apps, osv, admin_token):
    body = (await client.get(BYCVE, params={"id": "CVE-2023-1111"}, headers=_h(admin_token))).json()
    pkg = body["packages"][0]
    assert pkg["mode"] == "range_unevaluated" and pkg["ranges"] == ["< 4.17.21"]
    # both versions listed: ranges are NOT evaluated
    assert sorted(m["version"] for m in pkg["matches"]) == ["4.17.20", "4.17.21"]


@pytest.mark.asyncio
async def test_by_cve_unknown_invalid_and_upstream_errors(client, cve_apps, osv, admin_token):
    h = _h(admin_token)
    assert (await client.get(BYCVE, params={"id": "CVE-2099-0001"}, headers=h)).status_code == 404
    assert (await client.get(BYCVE, params={"id": "not-a-cve"}, headers=h)).status_code == 422
    assert (await client.get(BYCVE, params={"id": "CVE-1-1; DROP"}, headers=h)).status_code == 422
    osv.state["mode"] = "timeout"
    r = await client.get(BYCVE, params={"id": "CVE-2021-44228"}, headers=h)
    assert r.status_code == 424 and "in time" in r.json()["detail"]
    osv.state["mode"] = "500"
    r = await client.get(BYCVE, params={"id": "CVE-2021-44228"}, headers=h)
    assert r.status_code == 424 and "HTTP 500" in r.json()["detail"]


@pytest.mark.asyncio
async def test_by_cve_alias_failure_is_partial(client, cve_apps, osv, admin_token):
    del osv.db["GHSA-jfh8-c2jp-5v3q"]  # alias 404s
    body = (await client.get(BYCVE, params={"id": "CVE-2021-44228"}, headers=_h(admin_token))).json()
    assert body["partial"] is True and body["packages"] == []


@pytest.mark.asyncio
async def test_by_cve_sends_only_ids_to_osv_and_caches(client, cve_apps, osv, admin_token):
    h = _h(admin_token)
    await client.get(BYCVE, params={"id": "CVE-2021-44228"}, headers=h)
    paths = [r.url.path for r in osv.seen]
    assert paths == ["/v1/vulns/CVE-2021-44228", "/v1/vulns/GHSA-jfh8-c2jp-5v3q"]
    for req in osv.seen:  # no query string, no body, no app data, no auth header
        assert req.method == "GET" and not req.url.query and not req.content
        blob = (str(req.url) + str(dict(req.headers))).lower()
        assert all(w not in blob for w in ("shop", "billing", "lodash", "log4j-core", "bearer"))
    await client.get(BYCVE, params={"id": "CVE-2021-44228"}, headers=h)
    assert len(osv.seen) == 2  # second call served from the in-process cache


@pytest.mark.asyncio
async def test_by_cve_requires_admin(client, cve_apps, osv, dev_token):
    assert (await client.get(BYCVE, params={"id": "CVE-2021-44228"})).status_code == 401
    assert (await client.get(BYCVE, params={"id": "CVE-2021-44228"}, headers=_h(dev_token))).status_code == 403
    assert osv.seen == []


def test_osv_helpers():
    assert sbom_service._purl_prefixes("PyPI", "Django_Rest.Framework") == ["pkg:pypi/django-rest-framework"]
    assert sbom_service._purl_prefixes("Go", "github.com/x/y") == ["pkg:golang/github.com/x/y"]
    assert sbom_service._purl_prefixes("npm", "@babel/core") == ["pkg:npm/@babel/core", "pkg:npm/%40babel/core"]
    assert sbom_service._norm_version("Go", "v1.2.3") == "1.2.3"


SCOPED = {"id": "CVE-2024-2222", "aliases": ["GHSA-scoped"], "affected": []}
SCOPED_GHSA = {"id": "GHSA-scoped", "affected": [{"package": {"ecosystem": "npm", "name": "@babel/traverse"},
                                                  "versions": ["7.0.0"]}]}
MIXED = {"id": "CVE-2024-3333", "aliases": ["GHSA-mixed"], "affected": [
    {"package": {"ecosystem": "npm", "name": "lodash"}, "versions": ["4.17.20"]}]}
MIXED_GHSA = {"id": "GHSA-mixed", "affected": [{"package": {"ecosystem": "npm", "name": "lodash"},
              "ranges": [{"type": "SEMVER", "events": [{"introduced": "0"}, {"fixed": "4.17.21"}]}]}]}


@pytest.mark.asyncio
async def test_by_cve_scoped_npm_purl_is_percent_encoded(client, app_row, osv, admin_token):
    osv.db.update({"CVE-2024-2222": SCOPED, "GHSA-scoped": SCOPED_GHSA})
    comp = {"purl": "pkg:npm/%40babel/traverse@7.0.0", "name": "@babel/traverse", "version": "7.0.0",
            "ecosystem": "npm", "direct": False, "licenses": []}
    await _post(client, app_row.id, _payload(app_row.id, 1, [comp]))
    body = (await client.get(BYCVE, params={"id": "CVE-2024-2222"}, headers=_h(admin_token))).json()
    assert [m["app_name"] for m in body["packages"][0]["matches"]] == ["Shop"]


@pytest.mark.asyncio
async def test_by_cve_explicit_list_plus_unlisted_range_falls_back_to_unevaluated(client, cve_apps, osv, admin_token):
    osv.db.update({"CVE-2024-3333": MIXED, "GHSA-mixed": MIXED_GHSA})
    pkg = (await client.get(BYCVE, params={"id": "CVE-2024-3333"}, headers=_h(admin_token))).json()["packages"][0]
    assert pkg["mode"] == "range_unevaluated"
    assert sorted(m["version"] for m in pkg["matches"]) == ["4.17.20", "4.17.21"]  # nobody silently dropped


@pytest.mark.asyncio
async def test_coverage_counts_truncated_apps(client, app_row, admin_token):
    await _post(client, app_row.id, _payload(app_row.id, truncated=True))
    cov = (await client.get(SEARCH, headers=_h(admin_token))).json()["coverage"]
    assert cov["truncated_apps"] == 1


@pytest.mark.asyncio
async def test_chunked_oversize_body_is_rejected(client, app_row):
    async def chunks():  # no Content-Length: the cap must apply while streaming
        for _ in range(3):
            yield b"x" * (1024 * 1024)
    r = await client.post(HOOK, content=chunks(), headers={"X-CNP-Token": compute_token(app_row.id)})
    assert r.status_code == 413


@pytest.mark.asyncio
async def test_deeply_nested_json_is_422_not_500(client, app_row):
    r = await client.post(HOOK, content=b"[" * 200000 + b"]" * 200000, headers={"X-CNP-Token": compute_token(app_row.id)})
    assert r.status_code == 422
