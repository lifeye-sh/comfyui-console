"""V2.1 短剧项目、创作简报与用户隔离 API 测试。"""
from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _login(username: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _new_user() -> dict[str, str]:
    admin = _login("admin", "admin123")
    username = f"drama-{uuid4().hex[:12]}"
    response = client.post(
        "/api/v1/users",
        json={"username": username, "password": "user12345", "role": "user"},
        headers=admin,
    )
    assert response.status_code == 201
    return _login(username, "user12345")


def _create_project(headers: dict[str, str], name: str = "测试短剧") -> dict:
    response = client.post(
        "/api/v2/short-drama/projects",
        headers=headers,
        json={
            "name": name,
            "synopsis": "一名记者追查失踪案。",
            "source_type": "idea",
            "brief": {
                "genre": "悬疑",
                "audience": "年轻观众",
                "tone": "紧张",
                "platform": "竖屏平台",
                "aspect_ratio": "9:16",
                "episode_count": 8,
                "episode_duration": 90,
                "quality_tier": "draft",
                "visual_style": "冷色电影感",
                "constraints": {"ending": "保留反转"},
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_project_crud_brief_and_overview() -> None:
    headers = _new_user()
    project = _create_project(headers, "迷雾档案")

    listing = client.get("/api/v2/short-drama/projects?page=1&page_size=20", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["name"] == "迷雾档案"
    assert listing.json()["items"][0]["episode_count"] == 0

    brief = client.get(f"/api/v2/short-drama/projects/{project['id']}/brief", headers=headers)
    assert brief.status_code == 200
    assert brief.json()["episode_count"] == 8

    updated_brief = client.put(
        f"/api/v2/short-drama/projects/{project['id']}/brief",
        headers=headers,
        json={**brief.json(), "episode_count": 12, "lock_version": brief.json()["lock_version"]},
    )
    assert updated_brief.status_code == 200
    assert updated_brief.json()["episode_count"] == 12
    assert updated_brief.json()["lock_version"] == 2

    stale_brief = client.put(
        f"/api/v2/short-drama/projects/{project['id']}/brief",
        headers=headers,
        json={**brief.json(), "episode_count": 20, "lock_version": brief.json()["lock_version"]},
    )
    assert stale_brief.status_code == 409

    overview = client.get(f"/api/v2/short-drama/projects/{project['id']}/overview", headers=headers)
    assert overview.status_code == 200
    assert overview.json()["project"]["id"] == project["id"]
    assert overview.json()["brief"]["episode_count"] == 12
    assert overview.json()["shot_count"] == 0


def test_project_owner_isolation_and_optimistic_lock() -> None:
    owner = _new_user()
    stranger = _new_user()
    project = _create_project(owner, "归属隔离")

    hidden = client.get(f"/api/v2/short-drama/projects/{project['id']}", headers=stranger)
    assert hidden.status_code == 404
    stranger_list = client.get("/api/v2/short-drama/projects", headers=stranger)
    assert stranger_list.status_code == 200
    assert stranger_list.json()["total"] == 0

    updated = client.patch(
        f"/api/v2/short-drama/projects/{project['id']}",
        headers=owner,
        json={"lock_version": project["lock_version"], "name": "归属隔离·新版"},
    )
    assert updated.status_code == 200
    assert updated.json()["lock_version"] == project["lock_version"] + 1

    stale = client.patch(
        f"/api/v2/short-drama/projects/{project['id']}",
        headers=owner,
        json={"lock_version": project["lock_version"], "name": "过期覆盖"},
    )
    assert stale.status_code == 409


def test_project_soft_delete_and_restore() -> None:
    headers = _new_user()
    project = _create_project(headers, "可恢复项目")

    deleted = client.delete(f"/api/v2/short-drama/projects/{project['id']}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["deleted_at"] is not None
    assert deleted.json()["status"] == "archived"

    active_list = client.get("/api/v2/short-drama/projects", headers=headers)
    assert active_list.json()["total"] == 0
    deleted_list = client.get("/api/v2/short-drama/projects?include_deleted=true", headers=headers)
    assert deleted_list.json()["total"] == 1

    restored = client.post(f"/api/v2/short-drama/projects/{project['id']}/restore", headers=headers)
    assert restored.status_code == 200
    assert restored.json()["deleted_at"] is None
    assert restored.json()["status"] == "draft"


def test_project_list_search_and_server_pagination() -> None:
    headers = _new_user()
    _create_project(headers, "分页项目甲")
    _create_project(headers, "分页项目乙")
    _create_project(headers, "另一个项目")

    first = client.get("/api/v2/short-drama/projects?page=1&page_size=2", headers=headers)
    second = client.get("/api/v2/short-drama/projects?page=2&page_size=2", headers=headers)
    assert first.status_code == 200
    assert first.json()["total"] == 3
    assert len(first.json()["items"]) == 2
    assert len(second.json()["items"]) == 1

    searched = client.get("/api/v2/short-drama/projects?keyword=分页&page=1&page_size=20", headers=headers)
    assert searched.status_code == 200
    assert searched.json()["total"] == 2
