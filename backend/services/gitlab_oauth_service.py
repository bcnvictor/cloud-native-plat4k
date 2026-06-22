from typing import Dict
from urllib.parse import urlencode

import httpx

from backend.core.config import settings


class GitLabOAuthService:
    def __init__(self):
        self.base = settings.GITLAB_BASE_URL.rstrip("/")

    def generate_authorization_url(self, state: str) -> str:
        params = {
            "client_id": settings.GITLAB_OAUTH_CLIENT_ID,
            "redirect_uri": settings.GITLAB_OAUTH_REDIRECT_URI,
            "response_type": "code",
            "scope": settings.GITLAB_OAUTH_SCOPES,
            "state": state,
        }
        return f"{self.base}/oauth/authorize?{urlencode(params)}"

    async def exchange_code(self, code: str) -> Dict:
        data = {
            "client_id": settings.GITLAB_OAUTH_CLIENT_ID,
            "client_secret": settings.GITLAB_OAUTH_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": settings.GITLAB_OAUTH_REDIRECT_URI,
        }
        return await self._request_token(data)

    async def refresh_access_token(self, refresh_token: str) -> Dict:
        data = {
            "client_id": settings.GITLAB_OAUTH_CLIENT_ID,
            "client_secret": settings.GITLAB_OAUTH_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "redirect_uri": settings.GITLAB_OAUTH_REDIRECT_URI,
        }
        return await self._request_token(data)

    async def _request_token(self, data: Dict) -> Dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base}/oauth/token", data=data, timeout=10)
            if not resp.is_success:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=502,
                    detail=f"GitLab OAuth token exchange failed ({resp.status_code}). "
                           "Check GITLAB_OAUTH_CLIENT_ID, GITLAB_OAUTH_CLIENT_SECRET and GITLAB_OAUTH_REDIRECT_URI.",
                )
            return resp.json()

    async def get_user(self, access_token: str) -> Dict:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base}/api/v4/user", headers=headers, timeout=10)
            if not resp.is_success:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=502,
                    detail=f"GitLab user profile fetch failed ({resp.status_code}).",
                )
            return resp.json()

    async def is_group_member(self, access_token: str, group_path: str, gitlab_user_id: int) -> bool:
        from urllib.parse import quote
        encoded = quote(group_path, safe="")
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base}/api/v4/groups/{encoded}/members/all/{gitlab_user_id}",
                headers=headers,
                timeout=10,
            )
            return resp.status_code == 200
