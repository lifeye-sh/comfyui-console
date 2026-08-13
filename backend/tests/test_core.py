"""CC-35 核心服务测试：认证、节点、批次、资源接口冒烟。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_login_admin() -> None:
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_wrong_password() -> None:
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_regular_user_can_read_generation_select_options() -> None:
    admin_token = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    username = "select-options-user"
    created = client.post(
        "/api/v1/users",
        json={"username": username, "password": "user12345", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    if created.status_code not in (201, 400):
        assert created.status_code == 201
    token = client.post("/api/v1/auth/login", json={"username": username, "password": "user12345"}).json()["access_token"]
    response = client.get("/api/v1/settings/select-options", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["image_size"]["default_value"]


def test_me_without_token() -> None:
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_me_with_token() -> None:
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    token = login.json()["access_token"]
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"


def test_generation_types_menu() -> None:
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    token = login.json()["access_token"]
    resp = client.get("/api/v1/generation-types/menu", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    menu = resp.json()
    assert "image" in menu
    assert "video" in menu
    assert "audio" in menu
    assert all(
        item["code"] == "motion_transfer" or any(param["key"] == "duration" for param in item["param_schema"])
        for item in menu["video"]
    )


def test_dashboard_summary() -> None:
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    token = login.json()["access_token"]
    resp = client.get("/api/v1/dashboard/summary", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert {"tasks", "nodes", "resources", "workflows", "trend", "recent_tasks"} <= data.keys()
    assert len(data["trend"]) == 7


def test_nodes_list() -> None:
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    token = login.json()["access_token"]
    resp = client.get("/api/v1/nodes", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_prompt_categories() -> None:
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    token = login.json()["access_token"]
    resp = client.get("/api/v1/prompt-categories", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    cats = resp.json()
    assert len(cats) > 0  # 种子分类


def test_audit_logs_admin_only() -> None:
    resp = client.get("/api/v1/audit-logs")
    assert resp.status_code == 401
