"""Rate limiting (slowapi), applied per route with @limiter.limit.

No global default limit: behind cloudflared and the frontend nginx, a limit shared by
every route would also have to absorb the UI's polling, and a wrong client IP would
make all users share one bucket. Limits go on the routes that need them (login).
"""
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def client_ip(request: Request) -> str:
    """Real client IP behind Cloudflare Tunnel and the frontend nginx.

    uvicorn sees nginx's address for every request. Cloudflare sets CF-Connecting-IP;
    nginx forwards it and appends to X-Forwarded-For. These headers can be forged by
    a client that reaches nginx without going through Cloudflare: it can then dodge
    the limit, but never lock out another IP's bucket more than it could by itself.
    """
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=client_ip)

# Password login: brute force protection. SSO GitLab and API keys are not concerned.
LOGIN_RATE_LIMIT = "10/minute"
