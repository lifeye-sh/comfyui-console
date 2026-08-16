"""V2.1 改编候选、人工草稿与不可变版本测试。"""
from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.main import app
from app.models import CreativeJob
from app.short_drama.worker import story_worker

client = TestClient(app)


def _login(username: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _new_user() -> dict[str, str]:
    admin = _login("admin", "admin123")
    username = f"screenplay-{uuid4().hex[:10]}"
    assert client.post("/api/v1/users", headers=admin, json={"username": username, "password": "user12345", "role": "user"}).status_code == 201
    return _login(username, "user12345")


def _ready_document(headers: dict[str, str]) -> tuple[int, int]:
    project = client.post("/api/v2/short-drama/projects", headers=headers, json={
        "name": "剧本工作台测试", "source_type": "novel",
        "brief": {"episode_count": 2, "episode_duration": 60},
    })
    assert project.status_code == 201
    project_id = project.json()["id"]
    text = """测试长篇

第一章 相遇

林夏：你终于来了。

周野走进空荡的车站。

第二章 追踪

两人发现身后一直有人跟踪。

林夏：不要回头。

第三章 反转

跟踪者摘下帽子，竟是失踪多年的哥哥。
""".encode()
    imported = client.post(
        f"/api/v2/short-drama/projects/{project_id}/imports", headers=headers,
        files={"file": ("screenplay-source.txt", text, "text/plain")},
    )
    assert imported.status_code == 202
    job_id = imported.json()["job"]["id"]
    with SessionLocal() as db:
        job = db.get(CreativeJob, job_id); assert job is not None
        job.status = "running"; db.commit()
    story_worker._process(job_id)
    document_id = imported.json()["document"]["id"]
    return project_id, document_id


def test_candidate_requires_confirmation_and_builds_screenplay() -> None:
    init_db()
    headers = _new_user()
    project_id, document_id = _ready_document(headers)

    source = client.get(f"/api/v2/short-drama/projects/{project_id}/documents/{document_id}/content", headers=headers)
    assert source.status_code == 200
    assert len(source.json()["chapters"]) == 3

    candidate = client.post(f"/api/v2/short-drama/projects/{project_id}/adaptation-candidates", headers=headers, json={
        "document_id": document_id, "chapter_start": 1, "chapter_end": 3, "episode_count": 2,
    })
    assert candidate.status_code == 201, candidate.text
    payload = candidate.json()
    assert payload["status"] == "pending"
    assert len(payload["options"]) == 5
    assert client.get(f"/api/v2/short-drama/projects/{project_id}/screenplay", headers=headers).json()["episodes"] == []

    confirmed = client.post(
        f"/api/v2/short-drama/projects/{project_id}/adaptation-candidates/{payload['id']}/confirm",
        headers=headers, json={"option_key": "balanced", "version_name": "均衡首版"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["version"] == 1
    assert confirmed.json()["is_current"] is True
    repeated = client.post(
        f"/api/v2/short-drama/projects/{project_id}/adaptation-candidates/{payload['id']}/confirm",
        headers=headers, json={"option_key": "balanced", "version_name": "不应重复"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["id"] == confirmed.json()["id"]

    screenplay = client.get(f"/api/v2/short-drama/projects/{project_id}/screenplay", headers=headers).json()
    assert len(screenplay["episodes"]) == 2
    assert sum(len(item["scenes"]) for item in screenplay["episodes"]) == 3
    assert screenplay["draft_changed"] is False
    assert screenplay["episodes"][0]["scenes"][0]["elements"][0]["type"] in {"dialogue", "action"}


def test_manual_edit_snapshot_reorder_and_restore_as_new_version() -> None:
    init_db()
    headers = _new_user()
    stranger = _new_user()
    project_id, document_id = _ready_document(headers)
    candidate = client.post(f"/api/v2/short-drama/projects/{project_id}/adaptation-candidates", headers=headers, json={
        "document_id": document_id, "chapter_start": 1, "chapter_end": 3, "episode_count": 2,
    }).json()
    first_version = client.post(
        f"/api/v2/short-drama/projects/{project_id}/adaptation-candidates/{candidate['id']}/confirm",
        headers=headers, json={"option_key": "faithful", "version_name": "忠实首版"},
    ).json()
    screenplay = client.get(f"/api/v2/short-drama/projects/{project_id}/screenplay", headers=headers).json()
    scene = screenplay["episodes"][0]["scenes"][0]
    edited = client.patch(f"/api/v2/short-drama/projects/{project_id}/scenes/{scene['id']}", headers=headers, json={
        "lock_version": scene["lock_version"], "heading": "人工修改场景", "content": "人工调整后的正文。",
        "elements": [{"type": "action", "text": "人工调整后的正文。"}],
    })
    assert edited.status_code == 200, edited.text
    stale = client.patch(f"/api/v2/short-drama/projects/{project_id}/scenes/{scene['id']}", headers=headers, json={
        "lock_version": scene["lock_version"], "heading": "过期修改",
    })
    assert stale.status_code == 409
    assert client.get(f"/api/v2/short-drama/projects/{project_id}/screenplay", headers=headers).json()["draft_changed"] is True

    second_version = client.post(f"/api/v2/short-drama/projects/{project_id}/versions", headers=headers, json={"name": "人工修订版"})
    assert second_version.status_code == 201
    assert second_version.json()["version"] == 2
    original = client.get(f"/api/v2/short-drama/projects/{project_id}/versions/{first_version['id']}", headers=headers).json()
    assert original["content"]["episodes"][0]["scenes"][0]["heading"] != "人工修改场景"

    restored = client.post(f"/api/v2/short-drama/projects/{project_id}/versions/{first_version['id']}/restore", headers=headers)
    assert restored.status_code == 200
    assert restored.json()["version"] == 3
    after_restore = client.get(f"/api/v2/short-drama/projects/{project_id}/screenplay", headers=headers).json()
    assert after_restore["episodes"][0]["scenes"][0]["heading"] == original["content"]["episodes"][0]["scenes"][0]["heading"]

    episode_ids = [item["id"] for item in after_restore["episodes"]]
    reordered = client.put(f"/api/v2/short-drama/projects/{project_id}/screenplay/reorder", headers=headers, json={
        "episode_ids": list(reversed(episode_ids)), "scene_ids_by_episode": {},
    })
    assert reordered.status_code == 200
    assert reordered.json()["episodes"][0]["id"] == episode_ids[-1]
    assert client.get(f"/api/v2/short-drama/projects/{project_id}/versions", headers=stranger).status_code == 404
