import logging

from gitlab.exceptions import GitlabAuthenticationError, GitlabCreateError, GitlabGetError

import gitlab
from backend.core.config import settings

logger = logging.getLogger(__name__)


class GitLabClient:
    def __init__(
        self,
        token: str,
        namespace: str,
        base_url: str | None = None,
        use_private_token: bool = False,
    ):
        if base_url is None:
            base_url = settings.GITLAB_BASE_URL
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
        """Resolve namespace to its numeric ID.

        Groups and subgroups are resolved via the groups API (supports full paths
        with slashes). Personal namespaces fall back to the namespaces search API.
        """
        return self.get_namespace_id_for(self.namespace)

    def get_namespace_id_for(self, path: str) -> int | None:
        """Resolve an arbitrary namespace path to its numeric GitLab ID."""
        try:
            group = self._gl.groups.get(path)
            return group.id
        except Exception:
            pass
        try:
            namespaces = self._gl.namespaces.list(search=path, all=True)
            for ns in namespaces:
                if ns.full_path == path:
                    return ns.id
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

    def list_namespace_projects(self, namespace_path: str) -> list[dict]:
        """List projects directly under a group/subgroup path."""
        group = self._gl.groups.get(namespace_path)
        projects = group.projects.list(all=True, include_subgroups=False)
        return [
            {
                "name": p.name,
                "path": p.path,
                "web_url": p.web_url,
            }
            for p in projects
        ]

    def get_project(self, path_with_namespace: str):
        """Get a GitLab project by its full path (e.g. 'namespace/project')."""
        return self._gl.projects.get(path_with_namespace)

    def get_default_branch(self, project_path: str) -> str:
        """Return the default branch name of the project (falls back to 'main')."""
        project = self.get_project(project_path)
        return getattr(project, "default_branch", None) or "main"

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

    def push_multiple_files(
        self,
        project_path: str,
        branch: str,
        commit_message: str,
        actions: list[dict],
    ) -> None:
        """Commit multiple files in one atomic operation.

        Callers may use action="upsert" to mean create-or-update; this method
        resolves the correct GitLab action (create vs update) for each file.
        """
        project = self.get_project(project_path)
        resolved = []
        for action in actions:
            a = dict(action)
            if a.get("action") == "upsert":
                exists = self.file_exists(project_path, a["file_path"], ref=branch)
                a["action"] = "update" if exists else "create"
            resolved.append(a)
        project.commits.create({
            "branch": branch,
            "commit_message": commit_message,
            "actions": resolved,
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

    def register_webhook(self, project_path: str, webhook_url: str, secret_token: str = "") -> None:
        """Register a pipeline webhook on the project. No-op if already registered."""
        project = self.get_project(project_path)
        existing = project.hooks.list(all=True)
        for hook in existing:
            if hook.url == webhook_url:
                return
        project.hooks.create({
            "url": webhook_url,
            "pipeline_events": True,
            "token": secret_token,
            "enable_ssl_verification": not webhook_url.startswith("http://"),
        })

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
    
    @staticmethod
    def _slugify(name: str) -> str:
        import re
        slug = name.lower()
        slug = re.sub(r"[^a-z0-9_.-]", "-", slug)
        slug = re.sub(r"-{2,}", "-", slug)
        slug = slug.strip("-_.")
        return slug or "app"

    def delete_project(self, project_path: str) -> None:
        """Delete a GitLab project by its full path. No-op if not found."""
        try:
            project = self.get_project(project_path)
            project.delete()
        except GitlabGetError:
            pass

    def push_files_batch(
        self,
        project_path: str,
        files: list[dict],
        commit_message: str,
        branch: str = "main",
    ) -> None:
        """Push multiple files in a single commit using the GitLab Commits API.

        Each entry in `files` must have {"file_path": str, "content": str}.
        Uses "create" action — intended for repos with no prior commits.
        """
        project = self.get_project(project_path)
        actions = [
            {"action": "create", "file_path": f["file_path"], "content": f["content"]}
            for f in files
        ]
        project.commits.create({
            "branch": branch,
            "commit_message": commit_message,
            "actions": actions,
        })

    def create_project(self, name: str, namespace_id: int, initialize_with_readme: bool = False) -> dict:
        """Creates a new GitLab project in the specified namespace."""
        project = self._gl.projects.create({
            "name": name,
            "path": self._slugify(name),
            "namespace_id": namespace_id,
            "initialize_with_readme": initialize_with_readme,
            "default_branch": "main",
            "visibility": "private",
        })
        return {
            "id": project.id,
            "name": project.name,
            "path_with_namespace": project.path_with_namespace,
            "web_url": project.web_url,
        }

    def read_file(self, project_path: str, file_path: str, ref: str = "main") -> str:
        """Reads the contents of a file from the repository (decoded in UTF-8)."""
        project = self.get_project(project_path)
        raw = project.files.raw(file_path=file_path, ref=ref)
        if isinstance(raw, bytes):
            return raw.decode("utf-8")
        return raw

    def list_tree_recursive(self, project_path: str, ref: str = "main") -> list[dict]:
        """List all files in the repo recursively."""
        project = self.get_project(project_path)
        items = project.repository_tree(ref=ref, recursive=True, all=True)
        return [{"name": i["name"], "type": i["type"], "path": i["path"]} for i in items]

    def add_project_member(self, project_id: int, gitlab_user_id: int, access_level: int) -> None:
        """Add or update a user's membership on a GitLab project (by numeric IDs)."""
        project = self._gl.projects.get(project_id)
        try:
            project.members.create({"user_id": gitlab_user_id, "access_level": access_level})
        except Exception:
            member = project.members.get(gitlab_user_id)
            member.access_level = access_level
            member.save()

    def invite_project_member(self, project_id: int, email: str, access_level: int) -> None:
        """Send a GitLab project invitation to an email address."""
        project = self._gl.projects.get(project_id)
        project.invitations.create({"email": email, "access_level": access_level})

    def delete_directory_contents(self, project_path: str, directory_path: str, commit_message: str, branch: str = "main") -> None:
        """Deletes all files within a directory using the Commits API."""
        try:
            project = self.get_project(project_path)
            items = project.repository_tree(path=directory_path, ref=branch, recursive=True, all=True)
            actions = []
            for item in items:
                if item["type"] == "blob":
                    actions.append({"action": "delete", "file_path": item["path"]})

            if not actions:
                return

            project.commits.create({
                "branch": branch,
                "commit_message": commit_message,
                "actions": actions,
            })
        except Exception:
            logger.exception("Failed to delete directory %s in %s", directory_path, project_path)
