"""V2.1 AI 短剧模块骨架测试。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_short_drama_status_requires_authentication() -> None:
    response = client.get("/api/v2/short-drama/status")
    assert response.status_code == 401


def test_short_drama_foundation_status() -> None:
    response = client.get("/api/v2/short-drama/status", headers=_admin_headers())

    assert response.status_code == 200
    assert response.json() == {
        "enabled": settings.short_drama_enabled,
        "version": "2.1",
        "stage": "production",
        "capabilities": {
            "projects": True,
            "story_import": True,
            "story_bible": False,
            "storyboard": True,
            "task_bridge": True,
            "screenplay": True,
            "world_setting": True,
            "ai_adaptation": True,
        },
    }
