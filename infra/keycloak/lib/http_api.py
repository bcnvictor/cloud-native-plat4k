"""Small bounded JSON client; upstream bodies and credentials never enter errors."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class APIError(RuntimeError):
    def __init__(self, status: int):
        self.status = status
        super().__init__(f"API request failed (HTTP {status})")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


class JSONAPI:
    def __init__(self, url: str, headers: dict | None = None):
        parsed = urlsplit(url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Invalid API endpoint")
        self.url = url.rstrip("/")
        self.headers = headers or {}
        self.opener = build_opener(NoRedirect())

    def request(self, method: str, path: str, body=None, *, missing_ok=False, form=False):
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("API path must be relative")
        if form:
            from urllib.parse import urlencode

            payload = urlencode(body).encode()
        else:
            payload = json.dumps(body).encode() if body is not None else None
        headers = {
            "Content-Type": "application/x-www-form-urlencoded" if form else "application/json",
            **self.headers,
        }
        try:
            with self.opener.open(
                Request(self.url + path, data=payload, method=method, headers=headers), timeout=15
            ) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise RuntimeError("API response exceeds limit")
                return json.loads(raw) if raw else None
        except HTTPError as exc:
            if exc.code == 404 and missing_ok:
                return None
            raise APIError(exc.code) from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise RuntimeError("API unavailable or invalid response") from None
