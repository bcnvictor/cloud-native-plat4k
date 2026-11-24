"""CI dependency inventory (SBOM, library components only) — latest snapshot per app.

Ingestion (webhook ci-sbom, same HMAC token as the security report) replaces all components of an
app in one transaction. Search answers "which apps use this dependency?" for admins.
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Optional
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Application, GitLabGroup, SbomComponent, SbomSnapshot

MAX_COMPONENTS = 5000
MAX_SEARCH_LIMIT = 200
_INSERT_CHUNK = 500


class SbomComponentIn(BaseModel):
    # Unknown fields are dropped (pydantic default extra=ignore): only what we need is stored.
    purl: str = Field(min_length=1, max_length=500)
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=100)
    ecosystem: str = Field(pattern=r"^[a-z0-9._-]{1,32}$")
    direct: Optional[bool] = None
    licenses: list[str] = Field(default=[], max_length=10)

    def clean_licenses(self) -> list[str]:
        return [lic[:100] for lic in self.licenses if lic]


class SbomPayload(BaseModel):
    app_id: int
    pipeline_id: int = Field(ge=0, le=2**62)
    commit_sha: str = Field(max_length=64)
    components: list[SbomComponentIn] = Field(max_length=MAX_COMPONENTS)
    truncated: bool = False


class SbomService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ingest(self, payload: SbomPayload) -> bool:
        """Replace the app's inventory. Returns False when ignored (replay or older pipeline)."""
        app_id = payload.app_id
        # FOR UPDATE: two concurrent pipelines of the same app are serialized (no-op on SQLite).
        snap = (await self.db.execute(
            select(SbomSnapshot).where(SbomSnapshot.app_id == app_id).with_for_update())).scalar_one_or_none()
        if snap is not None and payload.pipeline_id <= snap.pipeline_id:
            return False
        # Dedupe on purl+version (a lockfile may list the same package twice): keep first occurrence.
        seen: set[tuple[str, str]] = set()
        rows: list[dict[str, Any]] = []
        for c in payload.components:
            key = (c.purl, c.version)
            if key in seen:
                continue
            seen.add(key)
            rows.append({"app_id": app_id, "name": c.name, "version": c.version, "ecosystem": c.ecosystem,
                         "purl": c.purl, "direct": c.direct, "licenses": c.clean_licenses()})
        try:
            await self.db.execute(delete(SbomComponent).where(SbomComponent.app_id == app_id))
            for i in range(0, len(rows), _INSERT_CHUNK):
                await self.db.execute(SbomComponent.__table__.insert(), rows[i:i + _INSERT_CHUNK])
            if snap is None:
                self.db.add(SbomSnapshot(app_id=app_id, pipeline_id=payload.pipeline_id,
                                         commit_sha=payload.commit_sha, component_count=len(rows),
                                         truncated=payload.truncated))
            else:
                snap.pipeline_id, snap.commit_sha = payload.pipeline_id, payload.commit_sha
                snap.component_count, snap.truncated = len(rows), payload.truncated
                snap.received_at = func.now()
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            # Concurrent first snapshot for the same app: the other one won, treat this one as a replay.
            # Any other integrity error (e.g. the app was deleted meanwhile) is a real failure.
            if (await self.db.execute(select(SbomSnapshot.app_id).where(SbomSnapshot.app_id == app_id))).first():
                return False
            raise
        return True

    async def coverage(self) -> dict[str, Any]:
        apps_total = (await self.db.execute(select(func.count(Application.id)))).scalar_one()
        n, oldest, newest, truncated = (await self.db.execute(
            select(func.count(SbomSnapshot.app_id), func.min(SbomSnapshot.received_at),
                   func.max(SbomSnapshot.received_at),
                   func.coalesce(func.sum(case((SbomSnapshot.truncated.is_(True), 1), else_=0)), 0)))).one()
        return {"apps_total": apps_total, "apps_with_sbom": n, "oldest_snapshot": oldest, "newest_snapshot": newest,
                "truncated_apps": int(truncated)}

    async def search(self, q: Optional[str], version: Optional[str], ecosystem: Optional[str],
                     limit: int, offset: int) -> dict[str, Any]:
        """Case-insensitive 'contains' on the package name; version/ecosystem are exact matches."""
        limit = max(1, min(limit, MAX_SEARCH_LIMIT))
        conds = []
        if q:
            esc = q.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conds.append(func.lower(SbomComponent.name).like(f"%{esc}%", escape="\\"))
        if version:
            conds.append(SbomComponent.version == version)
        if ecosystem:
            conds.append(SbomComponent.ecosystem == ecosystem)
        total = (await self.db.execute(select(func.count()).select_from(SbomComponent).where(*conds))).scalar_one()
        res = await self.db.execute(
            select(SbomComponent, Application.name, Application.slug, GitLabGroup.name, GitLabGroup.full_path)
            .join(Application, Application.id == SbomComponent.app_id)
            .outerjoin(GitLabGroup, GitLabGroup.gitlab_group_id == Application.owning_gitlab_group_id)
            .where(*conds)
            .order_by(func.lower(SbomComponent.name), SbomComponent.version, Application.name, SbomComponent.id)
            .limit(limit).offset(offset)
        )
        items = [
            {"app_id": c.app_id, "app_name": app_name, "app_slug": app_slug, "group": group_name,
             # same rule as the frontend (groupsApi.getSlug): last segment of the GitLab group path
             "group_slug": group_path.rsplit("/", 1)[-1] if group_path else None, "package": c.name,
             "version": c.version, "ecosystem": c.ecosystem, "direct": c.direct, "licenses": c.licenses or []}
            for c, app_name, app_slug, group_name, group_path in res.all()
        ]
        return {"items": items, "total": total, "limit": limit, "offset": offset, "coverage": await self.coverage()}


# ── Search by CVE (OSV.dev) ───────────────────────────────────────────────────
#
# OSV API: GET /v1/vulns/{id} returns a vulnerability by id. A CVE id resolves directly, but the
# CVE record often has no package data (e.g. CVE-2021-44228: GIT ranges only); the package-level
# `affected[]` (ecosystem, name, explicit `versions`, `ranges`) lives in the alias records
# (GHSA…) listed in `aliases`. We fetch the CVE, then its aliases, and merge their `affected[]`.
# Only vulnerability ids leave the platform: never any app data.

OSV_BASE_URL = "https://api.osv.dev"
OSV_TIMEOUT = 5.0
OSV_CACHE_TTL = 600.0
_OSV_CACHE_MAX = 256
_MAX_ALIASES = 8
MAX_OSV_PACKAGES = 50
CVE_RE = re.compile(r"^CVE-\d{4}-\d{4,9}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")

# inventory ecosystem (purl type) -> OSV ecosystem; only what the inventory can contain.
OSV_ECOSYSTEMS = {"npm": "npm", "pypi": "PyPI", "golang": "Go", "maven": "Maven",
                  "cargo": "crates.io", "gem": "RubyGems"}
_PURL_TYPE_BY_OSV = {v: k for k, v in OSV_ECOSYSTEMS.items()}

_osv_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class OsvError(Exception):
    """OSV lookup failed. status 404 = unknown vulnerability, 424 = upstream problem."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code, self.message = status_code, message


def _osv_client() -> httpx.AsyncClient:
    """Overridden in tests (MockTransport)."""
    return httpx.AsyncClient(base_url=OSV_BASE_URL, timeout=OSV_TIMEOUT, headers={"User-Agent": "cnp-backend"})


async def _fetch_vuln(client: httpx.AsyncClient, vuln_id: str) -> dict[str, Any]:
    hit = _osv_cache.get(vuln_id)
    if hit and time.monotonic() - hit[0] < OSV_CACHE_TTL:
        return hit[1]
    try:
        resp = await client.get(f"/v1/vulns/{vuln_id}")
    except httpx.TimeoutException as exc:
        raise OsvError(424, "OSV.dev did not answer in time, try again later.") from exc
    except httpx.HTTPError as exc:
        raise OsvError(424, "OSV.dev is unreachable, try again later.") from exc
    if resp.status_code == 404:
        raise OsvError(404, f"{vuln_id} is unknown to OSV.dev.")
    if resp.status_code != 200:
        raise OsvError(424, f"OSV.dev failed (HTTP {resp.status_code}), try again later.")
    try:
        data = resp.json()
    except ValueError as exc:
        raise OsvError(424, "OSV.dev returned an unreadable answer, try again later.") from exc
    if not isinstance(data, dict):
        raise OsvError(424, "OSV.dev returned an unreadable answer, try again later.")
    if len(_osv_cache) >= _OSV_CACHE_MAX:
        _osv_cache.clear()
    _osv_cache[vuln_id] = (time.monotonic(), data)
    return data


def _range_text(rng: dict[str, Any]) -> Optional[str]:
    """Human text of a SEMVER/ECOSYSTEM range (GIT ranges are commit hashes: not package versions)."""
    if rng.get("type") not in ("SEMVER", "ECOSYSTEM"):
        return None
    parts = []
    for ev in rng.get("events") or []:
        for key, label in (("introduced", ">="), ("fixed", "<"), ("last_affected", "<="), ("limit", "limit")):
            if key in ev:
                parts.append("all versions" if key == "introduced" and ev[key] == "0" else f"{label} {ev[key]}")
    text = ", ".join(p for p in parts if p != "all versions") or ("all versions" if parts else "")
    return text or None


def _osv_packages(records: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """Merge affected[] of all records by (OSV ecosystem, name), keeping inventory-relevant ecosystems."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for rec in records:
        for aff in rec.get("affected") or []:
            pkg = aff.get("package") or {}
            eco, name = pkg.get("ecosystem"), pkg.get("name")
            if eco not in _PURL_TYPE_BY_OSV or not isinstance(name, str) or not name:
                continue
            entry = out.setdefault((eco, name), {"versions": set(), "ranges": [], "unlisted": False})
            listed = [v for v in aff.get("versions") or [] if isinstance(v, str)]
            entry["versions"].update(listed)
            if not listed and any(isinstance(r, dict) and r.get("type") in ("SEMVER", "ECOSYSTEM")
                                  for r in aff.get("ranges") or []):
                entry["unlisted"] = True  # ranges without an explicit list: the list alone cannot be trusted
            for rng in aff.get("ranges") or []:
                text = _range_text(rng) if isinstance(rng, dict) else None
                if text and text not in entry["ranges"]:
                    entry["ranges"].append(text)
    return out


def _purl_prefixes(eco: str, name: str) -> list[str]:
    """purl prefixes (before '@') of an OSV package, per the purl spec of each ecosystem.

    Trivy percent-encodes segments (npm scope: `pkg:npm/%40babel/core`): both the encoded and the
    raw form are returned so neither spelling is missed."""
    ptype = _PURL_TYPE_BY_OSV[eco]
    if eco == "Maven":
        name = name.replace(":", "/", 1)
    elif eco == "PyPI":
        name = re.sub(r"[-_.]+", "-", name).lower()
    raw = f"pkg:{ptype}/{name}"
    encoded = f"pkg:{ptype}/" + "/".join(quote(seg, safe="") for seg in name.split("/"))
    return [raw] if raw == encoded else [raw, encoded]


def _norm_version(eco: str, v: str) -> str:
    return v[1:] if eco == "Go" and v.startswith("v") else v


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def search_by_cve(db: AsyncSession, cve_id: str) -> dict[str, Any]:
    """Which inventoried apps use a package affected by this CVE (via OSV.dev)? See module notes."""
    cve_id = cve_id.strip().upper()
    if not CVE_RE.match(cve_id):
        raise OsvError(422, "Expected a CVE identifier such as CVE-2021-44228.")
    partial = False
    async with _osv_client() as client:
        main = await _fetch_vuln(client, cve_id)
        aliases = [a for a in (main.get("aliases") or []) if isinstance(a, str) and _ID_RE.match(a)][:_MAX_ALIASES]
        records = [main]
        for res in await asyncio.gather(*(_fetch_vuln(client, a) for a in aliases), return_exceptions=True):
            if isinstance(res, dict):
                records.append(res)
            else:
                partial = True  # an alias could not be read: package data may be incomplete
    osv_pkgs = _osv_packages(records)
    packages = []
    ordered = sorted(osv_pkgs.items())
    if len(ordered) > MAX_OSV_PACKAGES:
        partial, ordered = True, ordered[:MAX_OSV_PACKAGES]  # bounded work per request
    for (eco, name), info in ordered:
        explicit = bool(info["versions"]) and not info["unlisted"]
        versions = {_norm_version(eco, v) for v in info["versions"]}
        prefixes = _purl_prefixes(eco, name)
        res = await db.execute(
            select(SbomComponent, Application.name, Application.slug, GitLabGroup.name, GitLabGroup.full_path)
            .join(Application, Application.id == SbomComponent.app_id)
            .outerjoin(GitLabGroup, GitLabGroup.gitlab_group_id == Application.owning_gitlab_group_id)
            .where(or_(*(func.lower(SbomComponent.purl).like(_like_escape(p.lower()) + "@%", escape="\\")
                         for p in prefixes)))
            .order_by(Application.name, SbomComponent.version)
        )
        matches = [
            {"app_id": c.app_id, "app_name": an, "app_slug": asl, "group": gn,
             "group_slug": gp.rsplit("/", 1)[-1] if gp else None, "package": c.name, "version": c.version,
             "ecosystem": c.ecosystem, "direct": c.direct, "licenses": c.licenses or []}
            for c, an, asl, gn, gp in res.all()
            if c.ecosystem == _PURL_TYPE_BY_OSV[eco] and (not explicit or _norm_version(eco, c.version) in versions)
        ]
        if matches:
            packages.append({"ecosystem": eco, "name": name,
                             "mode": "explicit" if explicit else "range_unevaluated",
                             "ranges": info["ranges"][:10], "matches": matches})
    return {
        "cve": cve_id,
        "summary": str(main.get("summary") or "")[:300] or None,
        "aliases": aliases,
        "osv_packages": len(osv_pkgs),
        "packages": packages,
        "partial": partial,
        "coverage": await SbomService(db).coverage(),
    }
