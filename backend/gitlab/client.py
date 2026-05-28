import gitlab
from gitlab.exceptions import GitlabAuthenticationError, GitlabGetError, GitlabCreateError


class GitLabClient:
    def __init__(
        self,
        token: str,
        namespace: str,
        base_url: str = "https://gitlab.cri.epita.fr",
        use_private_token: bool = False,
    ):
        if use_private_token:
            self._gl = gitlab.Gitlab(url=base_url, private_token=token)
        else:
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

    def get_project(self, path_with_namespace: str):
        """Get a GitLab project by its full path (e.g. 'namespace/project')."""
        return self._gl.projects.get(path_with_namespace)

    def list_tree(self, project_path: str, path: str = "", ref: str = "HEAD") -> list[dict]:
        """List files/dirs at the root (or given path) of a project."""
        project = self.get_project(project_path)
        items = project.repository_tree(path=path, ref=ref, all=True)
        return [{"name": item["name"], "type": item["type"], "path": item["path"]} for item in items]

    def push_file(
        self,
        project_path: str,
        file_path: str,
        content: str,
        commit_message: str,
        branch: str = "main",
    ) -> None:
        """Create or update a file in a project via commit."""
        project = self.get_project(project_path)
        try:
            f = project.files.get(file_path=file_path, ref=branch)
            f.content = content
            f.save(branch=branch, commit_message=commit_message)
        except GitlabGetError:
            project.files.create({
                "file_path": file_path,
                "branch": branch,
                "content": content,
                "commit_message": commit_message,
            })

    def create_branch(self, project_path: str, branch: str, ref: str = "main") -> None:
        """Create a branch from ref. Silently ignores if branch already exists."""
        project = self.get_project(project_path)
        try:
            project.branches.create({"branch": branch, "ref": ref})
        except GitlabCreateError:
            pass

    def file_exists(self, project_path: str, file_path: str, ref: str = "main") -> bool:
        """Return True if file_path exists in the project at ref."""
        project = self.get_project(project_path)
        try:
            project.files.get(file_path=file_path, ref=ref)
            return True
        except GitlabGetError:
            return False

    def create_mr(
        self,
        project_path: str,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str = "",
    ) -> dict:
        """Create a Merge Request and return its iid and web_url."""
        project = self.get_project(project_path)
        mr = project.mergerequests.create({
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
            "description": description,
        })
        return {"iid": mr.iid, "web_url": mr.web_url}
