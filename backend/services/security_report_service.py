"""CI security reports (trivy + gitleaks summary) — one stored row per app.

Token: HMAC-SHA256(SECRET_KEY, "ci-security-report:<app_id>"), recomputed on each call
(nothing stored). Grade: computed on read, see compute_grade().
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.models import SecurityReport

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")


def compute_token(app_id: int) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(), f"ci-security-report:{app_id}".encode(), hashlib.sha256
    ).hexdigest()


def verify_token(app_id: int, token: Optional[str]) -> bool:
    return bool(token) and hmac.compare_digest(compute_token(app_id), token)


def callback_url() -> str:
    return settings.CNP_CI_CALLBACK_URL or (
        f"{settings.CNP_API_BASE_URL.rstrip('/')}{settings.API_V1_STR}/webhooks/ci-security-report"
    )


def compute_grade(tools: dict[str, Any]) -> Optional[str]:
    """A→F from the stored summary; None when no tool produced a usable result.

    F: any secret leaked or any CRITICAL CVE · D: >=5 HIGH · C: 1-4 HIGH ·
    B: any MEDIUM · A: otherwise. A and B need both scanners ok (else None: a crashed
    scanner must not look clean).
    """
    trivy, leaks = tools.get("trivy") or {}, tools.get("gitleaks") or {}
    usable = [t for t in (trivy, leaks) if t.get("status") == "ok"]
    if not usable:
        return None
    counts = trivy.get("counts", {}) if trivy.get("status") == "ok" else {}
    secrets = leaks.get("counts", {}).get("total", 0) if leaks.get("status") == "ok" else 0
    if secrets > 0 or counts.get("CRITICAL", 0) > 0:
        return "F"
    high = counts.get("HIGH", 0)
    if high >= 5:
        return "D"
    if high >= 1:
        return "C"
    # A/B claim "nothing serious found": only valid when both scanners really ran.
    if len(usable) < 2:
        return None
    if counts.get("MEDIUM", 0) > 0:
        return "B"
    return "A"


class SecurityReportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, app_id: int) -> Optional[SecurityReport]:
        res = await self.db.execute(select(SecurityReport).where(SecurityReport.app_id == app_id))
        return res.scalar_one_or_none()

    async def upsert(self, app_id: int, pipeline_id: int, pipeline_url: str, commit_sha: str,
                     tools: dict[str, Any]) -> bool:
        """Store the report. Returns False when ignored (replay or older pipeline)."""
        row = await self.get(app_id)
        if row is None:
            self.db.add(SecurityReport(app_id=app_id, pipeline_id=pipeline_id, pipeline_url=pipeline_url,
                                       commit_sha=commit_sha, payload=tools))
        else:
            if pipeline_id <= row.pipeline_id:
                return False
            row.pipeline_id, row.pipeline_url, row.commit_sha = pipeline_id, pipeline_url, commit_sha
            row.payload = tools
            from sqlalchemy.sql import func
            row.received_at = func.now()
        try:
            await self.db.commit()
        except IntegrityError:
            # Concurrent first report for the same app: the other one won, treat this one as a replay.
            await self.db.rollback()
            return False
        return True

    @staticmethod
    def to_response(row: Optional[SecurityReport]) -> dict[str, Any]:
        if row is None:
            return {"report": None, "grade": None, "partial": False}
        tools = row.payload
        partial = any((tools.get(t) or {}).get("status") != "ok" for t in ("trivy", "gitleaks"))
        return {
            "report": {
                "pipeline_id": row.pipeline_id,
                "pipeline_url": row.pipeline_url,
                "commit_sha": row.commit_sha,
                "received_at": row.received_at,
                "tools": tools,
            },
            "grade": compute_grade(tools),
            "partial": partial,
        }
