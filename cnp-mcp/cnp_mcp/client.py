import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 15.0  # > budget de 8 s de /deployments côté backend


class CnpApiError(Exception):
    """Erreur lisible par le LLM ; `kind` vaut auth, not_found, unavailable ou client."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def _detail(resp: httpx.Response) -> str:
    try:
        detail = resp.json().get("detail")
    except Exception:
        return ""
    return detail if isinstance(detail, str) else ""


class CnpApiClient:
    def __init__(self, base_url: str, api_key: str):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                headers={"X-API-Key": self._api_key},
                timeout=_TIMEOUT,
            ) as http:
                resp = await http.get(path, params=params)
        except httpx.TimeoutException:
            raise CnpApiError("unavailable", "CNP source unavailable: timeout") from None
        except httpx.HTTPError as exc:
            raise CnpApiError("unavailable", f"CNP source unavailable: {type(exc).__name__}") from None
        elapsed_ms = (time.monotonic() - started) * 1000
        logger.info("GET %s -> %s (%.0f ms)", path, resp.status_code, elapsed_ms)

        status = resp.status_code
        if status in (401, 403):
            raise CnpApiError("auth", "CNP API key invalid, revoked or not allowed")
        if status == 404:
            raise CnpApiError("not_found", "not found")
        if status >= 500:
            reason = _detail(resp) or f"HTTP {status}"
            raise CnpApiError("unavailable", f"CNP source unavailable: {reason}")
        if status >= 400:
            reason = _detail(resp) or f"HTTP {status}"
            raise CnpApiError("client", f"CNP API rejected the request: {reason}")
        return resp.json()
