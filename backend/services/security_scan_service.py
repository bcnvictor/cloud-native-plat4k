import logging
import secrets
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.config import settings
from backend.db.models import (
    AISecurityFinding,
    AISecurityScan,
    Application,
    Event,
    Notification,
    User,
)
from backend.services.audit_service import AuditService

logger = logging.getLogger(__name__)


class SecurityScanService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def create_scan(
        self,
        app: Application,
        ref: str,
        triggered_by: User,
        trigger_ci: bool,
    ) -> AISecurityScan:
        scan = AISecurityScan(
            app_id=app.id,
            ref=ref,
            status="queued",
            triggered_by_user_id=triggered_by.id,
            callback_token=secrets.token_urlsafe(32),
        )
        self._db.add(scan)
        await self._db.flush()

        if trigger_ci and app.gitlab_project_id and settings.GITLAB_BOT_TOKEN:
            pipeline_id = self._trigger_pipeline(app, ref, scan)
            if pipeline_id:
                scan.gitlab_pipeline_id = pipeline_id
                scan.status = "running"

        await AuditService(self._db).log_action(
            user_id=triggered_by.id,
            action="security_scan.created",
            app_id=app.id,
            extra={"ref": ref, "trigger_ci": trigger_ci, "scan_id": scan.id},
        )

        await self._db.commit()
        await self._db.refresh(scan)
        return scan

    def _trigger_pipeline(self, app: Application, ref: str, scan: AISecurityScan) -> Optional[int]:
        from backend.gitlab.client import GitLabClient

        try:
            client = GitLabClient(
                token=settings.GITLAB_BOT_TOKEN,
                namespace=settings.GITLAB_BOT_NAMESPACE or "",
                use_private_token=True,
            )
            callback_base = getattr(settings, "BACKEND_URL", "")
            return client.trigger_scan_pipeline(
                gitlab_project_id=app.gitlab_project_id,
                ref=ref,
                variables={
                    "CNP_SCAN_ID": str(scan.id),
                    "CNP_CALLBACK_TOKEN": scan.callback_token,
                    "CNP_CALLBACK_URL": f"{callback_base}/api/v1/webhooks/security-scan-callback",
                },
            )
        except Exception as e:
            logger.warning("Could not trigger CI scan pipeline for app %s: %s", app.id, e)
            return None

    async def list_scans(self, app_id: int, limit: int = 20, offset: int = 0) -> list[AISecurityScan]:
        result = await self._db.execute(
            select(AISecurityScan)
            .where(AISecurityScan.app_id == app_id)
            .order_by(AISecurityScan.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_scan(self, scan_id: int, app_id: int) -> Optional[AISecurityScan]:
        result = await self._db.execute(
            select(AISecurityScan)
            .options(selectinload(AISecurityScan.findings))
            .where(AISecurityScan.id == scan_id, AISecurityScan.app_id == app_id)
        )
        return result.scalar_one_or_none()

    async def get_scan_by_token(self, scan_id: int, callback_token: str) -> Optional[AISecurityScan]:
        result = await self._db.execute(
            select(AISecurityScan)
            .options(selectinload(AISecurityScan.findings))
            .where(
                AISecurityScan.id == scan_id,
                AISecurityScan.callback_token == callback_token,
            )
        )
        return result.scalar_one_or_none()

    async def apply_callback(
        self,
        scan: AISecurityScan,
        status: str,
        findings: list[dict],
        error_message: Optional[str] = None,
    ) -> AISecurityScan:
        scan.status = status
        scan.error_message = error_message

        for raw in findings:
            finding = AISecurityFinding(
                scan_id=scan.id,
                tool=raw.get("tool", "unknown"),
                severity=raw.get("severity", "info"),
                title=raw.get("title", ""),
                description=raw.get("description"),
                file_path=raw.get("file_path"),
                line_start=raw.get("line_start"),
                line_end=raw.get("line_end"),
                confidence=raw.get("confidence"),
                remediation=raw.get("remediation"),
                status="open",
                raw_data=raw.get("raw_data"),
            )
            self._db.add(finding)

        await self._db.flush()

        critical_count = sum(1 for f in findings if f.get("severity") == "critical")
        if status == "completed" and critical_count > 0:
            await self._notify_critical(scan, critical_count)

        await self._db.commit()
        await self._db.refresh(scan)
        return scan

    async def _notify_critical(self, scan: AISecurityScan, critical_count: int) -> None:
        dedup_key = f"security-scan-{scan.id}-critical"
        existing = await self._db.execute(select(Event).where(Event.dedup_key == dedup_key))
        if existing.scalar_one_or_none():
            return

        event = Event(
            type="security.scan.critical",
            severity="critical",
            source="ai_security_scan",
            app_id=scan.app_id,
            payload={"scan_id": scan.id, "critical_count": critical_count, "ref": scan.ref},
            dedup_key=dedup_key,
        )
        self._db.add(event)
        await self._db.flush()

        if scan.triggered_by_user_id:
            notif = Notification(
                event_id=event.id,
                recipient_user_id=scan.triggered_by_user_id,
                state="new",
            )
            self._db.add(notif)
