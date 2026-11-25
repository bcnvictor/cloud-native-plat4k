from httpx import AsyncClient

from backend.core.config import settings

URL = "/api/v1/admin/platform-schedules"


async def test_admin_reads_worker_schedules(client: AsyncClient, admin_token: str, monkeypatch):
    monkeypatch.setattr(settings, "SCALE_SCHEDULE_ENABLED", True)
    monkeypatch.setattr(settings, "DEV_SCALE_DOWN_HOUR", 21)
    monkeypatch.setattr(settings, "DEV_SCALE_UP_HOUR", 7)
    monkeypatch.setattr(settings, "DEV_SCALE_TIMEZONE", "Europe/Paris")
    monkeypatch.setattr(settings, "DEV_SCALE_WEEKDAYS_ONLY", False)
    monkeypatch.setattr(settings, "GITLAB_SYNC_INTERVAL_MINUTES", 30)
    monkeypatch.setattr(settings, "GITLAB_BOT_TOKEN", "glpat-x")

    res = await client.get(URL, headers={"Authorization": f"Bearer {admin_token}"})

    assert res.status_code == 200
    body = res.json()
    assert body["scale_to_zero"] == {
        "enabled": True,
        "interval_minutes": settings.SCALE_SCHEDULE_INTERVAL_MINUTES,
        "scale_down_hour": 21,
        "scale_up_hour": 7,
        "timezone": "Europe/Paris",
        "weekdays_only": False,
    }
    assert body["gitlab_sync"] == {"enabled": True, "interval_minutes": 30}


async def test_gitlab_sync_reported_off_without_token(client: AsyncClient, admin_token: str, monkeypatch):
    monkeypatch.setattr(settings, "GITLAB_BOT_TOKEN", "")
    monkeypatch.setattr(settings, "GITLAB_TOKEN", "")

    res = await client.get(URL, headers={"Authorization": f"Bearer {admin_token}"})

    assert res.json()["gitlab_sync"]["enabled"] is False


async def test_non_admin_is_forbidden(client: AsyncClient, dev_token: str):
    res = await client.get(URL, headers={"Authorization": f"Bearer {dev_token}"})
    assert res.status_code == 403
