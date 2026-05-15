import gitlab
from gitlab.exceptions import GitlabAuthenticationError, GitlabGetError


class GitLabClient:
    def __init__(self, token: str, namespace: str, base_url: str = "https://gitlab.cri.epita.fr"):
        # OAuth access tokens must be passed as oauth_token, not private_token
        self._gl = gitlab.Gitlab(url=base_url, oauth_token=token)
        self.namespace = namespace
        self.base_url = base_url

    def healthcheck(self) -> dict:
        """Verify connectivity and token validity via GET /user."""
        try:
            self._gl.auth()
            user = self._gl.users.get(self._gl.user.id)
            return {
                "status": "ok",
                "gitlab_url": self.base_url,
                "authenticated_as": user.username,
            }
        except GitlabAuthenticationError as e:
            return {"status": "error", "detail": f"Authentication failed: {e}"}
        except GitlabGetError as e:
            return {"status": "error", "detail": f"GitLab API error: {e}"}
        except Exception as e:
            return {"status": "error", "detail": f"Unexpected error: {e}"}

    def get_namespace_id(self) -> int | None:
        """Resolve namespace to its numeric ID (group or user)."""
        try:
            groups = self._gl.groups.list(search=self.namespace)
            for g in groups:
                if g.full_path == self.namespace:
                    return g.id
            users = self._gl.users.list(username=self.namespace)
            if users:
                return users[0].id
        except Exception:
            pass
        return None

    def list_projects(self) -> list[dict]:
        """List projects accessible by the authenticated user."""
        projects = self._gl.projects.list(membership=True, per_page=100, all=True)
        return [
            {
                "id": p.id,
                "name": p.name,
                "path_with_namespace": p.path_with_namespace,
                "web_url": p.web_url,
                "last_activity_at": p.last_activity_at,
            }
            for p in projects
        ]
