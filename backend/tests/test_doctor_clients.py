"""CNP Doctor — ajouts aux clients Kubernetes et GitLab (horodatages, comparaison)."""
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

from backend.gitlab.client import GitLabClient
from backend.k8s.client import KubernetesClient


def test_pod_diagnostics_expose_timestamps_for_the_timeline():
    t0 = datetime(2026, 11, 16, 14, 2, 10, tzinfo=timezone.utc)
    t1 = datetime(2026, 11, 16, 14, 6, 48, tzinfo=timezone.utc)
    container = NS(
        name="app", ready=False, restart_count=6,
        state=NS(waiting=NS(reason="CrashLoopBackOff", message="back-off"), running=None),
        last_state=NS(terminated=NS(reason="Error", exit_code=1, finished_at=t1)),
    )
    pod = NS(metadata=NS(name="demo-shop-7d9f"),
             status=NS(phase="Running", start_time=t0, container_statuses=[container]))
    event = NS(involved_object=NS(name="demo-shop-7d9f"), reason="BackOff", message="restarting", count=9,
               first_timestamp=t0, last_timestamp=t1, event_time=None, metadata=NS(creation_timestamp=t0))

    k8s = KubernetesClient.__new__(KubernetesClient)
    k8s._apps_v1, k8s._core_v1 = MagicMock(), MagicMock()
    k8s._apps_v1.read_namespaced_deployment.return_value = NS(
        spec=NS(replicas=1, selector=NS(match_labels={"app": "demo-shop"})), status=NS(ready_replicas=None))
    k8s._core_v1.list_namespaced_pod.return_value = NS(items=[pod])
    k8s._core_v1.list_namespaced_event.return_value = NS(items=[event])

    diag = k8s.get_pod_diagnostics("prod", "demo-shop")

    assert diag["pods"][0]["start_time"] == t0.isoformat()
    assert diag["pods"][0]["containers"][0]["started_at"] is None
    assert diag["warnings"][0]["first_seen"] == t0.isoformat()
    assert diag["warnings"][0]["last_seen"] == t1.isoformat()


def test_compare_revisions_returns_titles_and_paths_only():
    project = MagicMock(web_url="https://gitlab.example/team/demo-shop")
    project.repository_compare.return_value = {
        "commits": [
            {"id": "9c8b7a6d" + "0" * 32, "short_id": "9c8b7a6d", "title": "chore: deps",
             "author_name": "Alice", "created_at": "2026-11-16T11:14:03Z", "web_url": "https://gl/c/1"},
            {"id": "f4e5d6c7" + "0" * 32, "short_id": "f4e5d6c7", "title": "feat(payment): client",
             "author_name": "Alice", "created_at": "2026-11-16T13:52:40Z", "web_url": "https://gl/c/2"},
        ],
        "diffs": [
            {"old_path": "app/config.py", "new_path": "app/config.py", "new_file": False,
             "renamed_file": False, "deleted_file": False, "diff": "@@ secret code @@"},
            {"old_path": "app/payment/client.py", "new_path": "app/payment/client.py", "new_file": True,
             "renamed_file": False, "deleted_file": False, "diff": "+ code"},
        ],
        "compare_timeout": False,
    }
    gl = GitLabClient.__new__(GitLabClient)
    gl._gl = MagicMock()
    gl._gl.projects.get.return_value = project

    result = gl.compare_revisions(4242, "a1b2c3d4" + "0" * 32, "f4e5d6c7" + "0" * 32, max_commits=1)

    project.repository_compare.assert_called_once_with("a1b2c3d4" + "0" * 32, "f4e5d6c7" + "0" * 32)
    assert result["compare_url"] == "https://gitlab.example/team/demo-shop/-/compare/a1b2c3d4...f4e5d6c7"
    assert [c["title"] for c in result["commits"]] == ["feat(payment): client"]   # le plus récent d'abord
    assert result["truncated"] is True
    assert result["files"] == [{"path": "app/config.py", "change": "modified"},
                               {"path": "app/payment/client.py", "change": "added"}]
    assert "diff" not in str(result)                                              # jamais le code
