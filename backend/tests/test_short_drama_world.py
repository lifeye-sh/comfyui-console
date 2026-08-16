"""V2.1 角色与世界设定、候选确认和引用完整性测试。"""
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


def _new_user(prefix: str = "world") -> dict[str, str]:
    admin = _login("admin", "admin123")
    username = f"{prefix}-{uuid4().hex[:10]}"
    response = client.post("/api/v1/users", headers=admin, json={"username": username, "password": "user12345", "role": "user"})
    assert response.status_code == 201
    return _login(username, "user12345")


def _screenplay(headers: dict[str, str]) -> tuple[int, dict]:
    created = client.post("/api/v2/short-drama/projects", headers=headers, json={"name": "世界设定测试", "source_type": "novel"})
    assert created.status_code == 201
    project_id = created.json()["id"]
    source = "第一章 相遇\n\n林夏来到旧车站。\n\n周野递给她一部手机。".encode("utf-8")
    imported = client.post(
        f"/api/v2/short-drama/projects/{project_id}/imports", headers=headers,
        files={"file": ("world.txt", source, "text/plain")},
    )
    assert imported.status_code == 202
    with SessionLocal() as db:
        job = db.get(CreativeJob, imported.json()["job"]["id"]); assert job is not None
        job.status = "running"; db.commit()
    story_worker._process(imported.json()["job"]["id"])
    candidate = client.post(f"/api/v2/short-drama/projects/{project_id}/adaptation-candidates", headers=headers, json={
        "document_id": imported.json()["document"]["id"], "chapter_start": 1, "chapter_end": 1, "episode_count": 1,
    })
    assert candidate.status_code == 201, candidate.text
    confirmed = client.post(
        f"/api/v2/short-drama/projects/{project_id}/adaptation-candidates/{candidate.json()['id']}/confirm",
        headers=headers, json={"option_key": "balanced", "version_name": "剧本首版"},
    )
    assert confirmed.status_code == 200, confirmed.text
    scene = client.get(f"/api/v2/short-drama/projects/{project_id}/screenplay", headers=headers).json()["episodes"][0]["scenes"][0]
    changed = client.patch(f"/api/v2/short-drama/projects/{project_id}/scenes/{scene['id']}", headers=headers, json={
        "lock_version": scene["lock_version"], "location_name": "旧车站", "time_of_day": "夜",
        "elements": [
            {"type": "dialogue", "speaker": "林夏", "text": "你终于来了。"},
            {"type": "dialogue", "speaker": "周野", "text": "先拿好手机。"},
            {"type": "action", "text": "周野把手机递给林夏。"},
        ],
    })
    assert changed.status_code == 200, changed.text
    assert client.post(f"/api/v2/short-drama/projects/{project_id}/versions", headers=headers, json={"name": "设定提取版"}).status_code == 201
    return project_id, changed.json()


def test_world_candidate_confirmation_preserves_manual_data_and_links_scenes() -> None:
    init_db(); headers = _new_user(); stranger = _new_user("world-other")
    project_id, scene = _screenplay(headers)

    preview = client.post(f"/api/v2/short-drama/projects/{project_id}/world-candidates", headers=headers)
    assert preview.status_code == 201, preview.text
    payload = preview.json()["payload"]
    assert {item["name"] for item in payload["characters"]} == {"林夏", "周野"}
    assert payload["locations"][0]["name"] == "旧车站"
    assert {payload["relationships"][0]["source_name"], payload["relationships"][0]["target_name"]} == {"林夏", "周野"}
    assert payload["props"][0]["name"] == "手机"
    assert payload["characters"][0]["source_references"]

    confirmed = client.post(
        f"/api/v2/short-drama/projects/{project_id}/world-candidates/{preview.json()['id']}/confirm",
        headers=headers, json={"skip_existing": True},
    )
    assert confirmed.status_code == 200, confirmed.text
    world = client.get(f"/api/v2/short-drama/projects/{project_id}/world", headers=headers)
    assert world.status_code == 200
    data = world.json(); assert len(data["characters"]) == 2 and len(data["locations"]) == 1 and len(data["relationships"]) == 1
    linked = client.get(f"/api/v2/short-drama/projects/{project_id}/screenplay", headers=headers).json()["episodes"][0]["scenes"][0]
    assert len(linked["character_ids"]) == 2 and linked["location_id"] == data["locations"][0]["id"]

    character = next(item for item in data["characters"] if item["name"] == "林夏")
    body = {key: character[key] for key in (
        "name", "aliases", "identity", "age_appearance", "appearance", "personality", "relationships",
        "negative_traits", "source_references", "reference_resource_ids", "primary_resource_id", "status",
    )}
    body["appearance"] = "人工锁定：红色风衣，短发"
    edited = client.put(f"/api/v2/short-drama/projects/{project_id}/characters/{character['id']}", headers=headers, json=body)
    assert edited.status_code == 200
    second = client.post(f"/api/v2/short-drama/projects/{project_id}/world-candidates", headers=headers).json()
    assert any(item["name"] == "林夏" for item in second["conflicts"])
    assert client.post(
        f"/api/v2/short-drama/projects/{project_id}/world-candidates/{second['id']}/confirm",
        headers=headers, json={"skip_existing": True},
    ).status_code == 200
    after = client.get(f"/api/v2/short-drama/projects/{project_id}/world", headers=headers).json()
    assert next(item for item in after["characters"] if item["name"] == "林夏")["appearance"] == body["appearance"]

    third = client.post(f"/api/v2/short-drama/projects/{project_id}/world-candidates", headers=headers).json()
    refused = client.post(
        f"/api/v2/short-drama/projects/{project_id}/world-candidates/{third['id']}/confirm",
        headers=headers, json={"skip_existing": False},
    )
    assert refused.status_code == 422
    assert client.get(f"/api/v2/short-drama/projects/{project_id}/world", headers=stranger).status_code == 404

    invalid_link = client.patch(f"/api/v2/short-drama/projects/{project_id}/scenes/{scene['id']}", headers=headers, json={
        "lock_version": linked["lock_version"], "character_ids": [99999999],
    })
    assert invalid_link.status_code == 422
    assert client.delete(f"/api/v2/short-drama/projects/{project_id}/characters/{character['id']}", headers=headers).status_code == 422


def test_manual_cards_variants_and_resource_ownership_validation() -> None:
    init_db(); headers = _new_user("world-manual")
    project = client.post("/api/v2/short-drama/projects", headers=headers, json={"name": "人工设定"}).json()
    character_body = {
        "name": "顾言", "aliases": ["阿言"], "identity": "调查记者", "age_appearance": "28岁",
        "appearance": "黑色夹克", "personality": "克制", "negative_traits": ["避免夸张表情"], "status": "confirmed",
    }
    character = client.post(f"/api/v2/short-drama/projects/{project['id']}/characters", headers=headers, json=character_body)
    assert character.status_code == 201, character.text
    variant = client.post(
        f"/api/v2/short-drama/projects/{project['id']}/characters/{character.json()['id']}/variants", headers=headers,
        json={"name": "雨夜造型", "wardrobe": "湿润黑色风衣", "hairstyle": "湿发"},
    )
    assert variant.status_code == 201, variant.text
    overview = client.get(f"/api/v2/short-drama/projects/{project['id']}/world", headers=headers).json()
    assert overview["characters"][0]["variants"][0]["name"] == "雨夜造型"
    invalid_resource = client.post(f"/api/v2/short-drama/projects/{project['id']}/locations", headers=headers, json={
        "name": "天台", "reference_resource_ids": [99999999],
    })
    assert invalid_resource.status_code == 422
    assert client.delete(
        f"/api/v2/short-drama/projects/{project['id']}/characters/{character.json()['id']}/variants/{variant.json()['id']}", headers=headers,
    ).status_code == 200
