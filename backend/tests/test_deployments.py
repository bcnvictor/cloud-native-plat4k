"""Endpoint /deployments : agrégation de l'historique ArgoCD, dégradation partielle, timeouts."""

from types import SimpleNamespace

from shared.models import DeploymentEnv

from backend.services.deployment_service import history_entry_to_deployment

APP = SimpleNamespace(id=42, slug="billing", name="Billing")


def _entry(history_id: int, deployed_at: str, **extra) -> dict:
    return {"id": history_id, "revision": f"sha{history_id}", "deployedAt": deployed_at, **extra}


# ── history_entry_to_deployment ───────────────────────────────────────────────

def test_entry_with_username_multi_source():
    d = history_entry_to_deployment(APP, DeploymentEnv.PROD, {
        "id": 17, "revisions": ["abc123", "def456"], "deployedAt": "2026-10-01T12:00:00Z",
        "deployStartedAt": "2026-10-01T11:59:30Z", "initiatedBy": {"username": "alice"},
    })
    assert d.id == "42:prod:17"
    assert (d.app_id, d.app_slug, d.app_name, d.history_id) == (42, "billing", "Billing", 17)
    assert d.revisions == ["abc123", "def456"]
    assert (d.initiated_by, d.automated) == ("alice", False)
    assert d.deploy_started_at is not None


def test_entry_automated_mono_source():
    d = history_entry_to_deployment(APP, DeploymentEnv.DEV, {
        "id": 3, "revision": "abc123", "deployedAt": "2026-10-01T12:00:00Z",
        "initiatedBy": {"automated": True},
    })
    assert d.revisions == ["abc123"]
    assert (d.initiated_by, d.automated) == (None, True)
    assert d.deploy_started_at is None


def test_entry_without_initiated_by():
    d = history_entry_to_deployment(APP, DeploymentEnv.DEV, _entry(1, "2026-10-01T12:00:00Z"))
    assert (d.initiated_by, d.automated) == (None, False)
