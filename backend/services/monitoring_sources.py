"""Which Prometheus / Loki to query: the app's target cluster, else the platform default.
Costs span every cluster: fan_out queries each Prometheus and skips unreachable ones."""
import asyncio
import logging
from typing import Awaitable, Callable, Optional, TypeVar
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from backend.core.config import settings
from backend.db.models import Application, ClusterConnection
from backend.services.cluster_service import ClusterService

logger = logging.getLogger(__name__)

FAN_OUT_TIMEOUT_SECONDS = 10

T = TypeVar("T")


def normalize_url(url: str) -> str:
    """Comparable form: trimmed, lowercase scheme and host, no trailing slash.
    Userinfo (user:password@) is kept as is: credentials are case-sensitive."""
    parts = urlsplit(url.strip())
    userinfo, at, hostport = parts.netloc.rpartition("@")
    return urlunsplit(
        (parts.scheme.lower(), f"{userinfo}{at}{hostport.lower()}", parts.path.rstrip("/"),
         parts.query, parts.fragment)
    )


async def _cluster_field(
    db: AsyncSession, field: str, cluster_id: Optional[int], app: Optional[Application]
) -> Optional[str]:
    cluster = None
    if cluster_id is not None:
        cluster = await ClusterService(db).get_cluster(cluster_id)
    elif app is not None and app.target_cluster_id:
        # db.get passe par l'identity map : pas de lazy load de app.target_cluster
        cluster = await db.get(ClusterConnection, app.target_cluster_id)
    value = (getattr(cluster, field) or "").strip() if cluster is not None else ""
    return value or None


async def resolve_prometheus_url(
    db: AsyncSession, *, cluster_id: Optional[int] = None, app: Optional[Application] = None
) -> str:
    return await _cluster_field(db, "prometheus_url", cluster_id, app) or settings.PROMETHEUS_URL


async def resolve_loki_url(
    db: AsyncSession, *, cluster_id: Optional[int] = None, app: Optional[Application] = None
) -> str:
    return await _cluster_field(db, "loki_url", cluster_id, app) or settings.LOKI_URL


async def app_by_slug(db: AsyncSession, slug: str) -> Optional[Application]:
    result = await db.execute(
        select(Application)
        .options(joinedload(Application.target_cluster))
        .where(Application.slug == slug)
    )
    return result.scalar_one_or_none()


async def prometheus_urls(db: AsyncSession) -> list[str]:
    """Every distinct Prometheus: the clusters' (by id), then the platform default.

    The default is only a fallback, for clusters without their own URL and for apps
    without a target cluster: it is left out when neither exists, so that a default
    spelled differently from a cluster's URL (DNS name vs IP) can't make that
    Prometheus count twice in the cost sums."""
    rows = await db.execute(select(ClusterConnection.prometheus_url).order_by(ClusterConnection.id))
    cluster_urls = list(rows.scalars().all())
    candidates = [u for u in cluster_urls if u and u.strip()]
    needs_default = len(candidates) < len(cluster_urls) or (
        await db.execute(select(Application.id).where(Application.target_cluster_id.is_(None)).limit(1))
    ).first() is not None
    if needs_default or not candidates:
        candidates.append(settings.PROMETHEUS_URL)
    urls: list[str] = []
    for url in candidates:
        if url and url.strip():
            normalized = normalize_url(url)
            if normalized not in urls:
                urls.append(normalized)
    return urls


async def fan_out(urls: list[str], fn: Callable[[str], Awaitable[T]]) -> list[T]:
    """fn(url) on every URL in parallel; failures are logged and skipped, unless all fail."""
    results = await asyncio.gather(
        *(asyncio.wait_for(fn(url), FAN_OUT_TIMEOUT_SECONDS) for url in urls),
        return_exceptions=True,
    )
    ok: list[T] = []
    last_error: Optional[BaseException] = None
    for url, result in zip(urls, results):
        if isinstance(result, BaseException):
            logger.warning("Prometheus %s ignoré : %s", url, type(result).__name__)
            last_error = result
        else:
            ok.append(result)
    if not ok and last_error is not None:
        raise last_error
    return ok
