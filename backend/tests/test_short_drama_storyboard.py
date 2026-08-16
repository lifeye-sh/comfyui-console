"""V2.1 scene-to-shot candidate and storyboard editing tests."""
from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app

client = TestClient(app)


def _login(username: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _new_user(prefix: str = "storyboard") -> dict[str, str]:
    admin = _login("admin", "admin123"); username = f"{prefix}-{uuid4().hex[:10]}"
    assert client.post("/api/v1/users", headers=admin, json={"username": username, "password": "user12345", "role": "user"}).status_code == 201
    return _login(username, "user12345")


def _project_scene(headers: dict[str, str]) -> tuple[int, int, int, list[int], int]:
    project = client.post("/api/v2/short-drama/projects", headers=headers, json={"name": "分镜测试", "brief": {"episode_count": 1, "episode_duration": 30}}).json(); project_id = project["id"]
    characters = []
    for name in ("林夏", "周野"):
        item = client.post(f"/api/v2/short-drama/projects/{project_id}/characters", headers=headers, json={"name": name, "status": "confirmed"})
        assert item.status_code == 201; characters.append(item.json()["id"])
    location = client.post(f"/api/v2/short-drama/projects/{project_id}/locations", headers=headers, json={"name": "旧车站", "status": "confirmed"})
    assert location.status_code == 201
    episode = client.post(f"/api/v2/short-drama/projects/{project_id}/episodes", headers=headers, json={"title": "相遇", "target_duration": 30})
    assert episode.status_code == 201
    scene = client.post(f"/api/v2/short-drama/projects/{project_id}/episodes/{episode.json()['id']}/scenes", headers=headers, json={
        "heading": "雨夜相遇", "location_name": "旧车站", "location_id": location.json()["id"], "character_ids": characters,
        "target_duration": 12, "elements": [
            {"type": "action", "text": "林夏走进雨中的旧车站。"},
            {"type": "dialogue", "speaker": "周野", "text": "你终于来了。"},
            {"type": "action", "text": "两人隔着站台对望。"},
        ],
    })
    assert scene.status_code == 201, scene.text
    version = client.post(f"/api/v2/short-drama/projects/{project_id}/versions", headers=headers, json={"name": "分镜来源版"})
    assert version.status_code == 201, version.text
    return project_id, episode.json()["id"], scene.json()["id"], characters, version.json()["id"]


def _patch_body(shot: dict, **changes: object) -> dict:
    keys = (
        "purpose", "visual_description", "action", "expression", "dialogue", "character_ids", "location_id", "prop_ids",
        "mood", "shot_size", "camera_angle", "camera_movement", "composition", "transition", "duration",
        "first_frame_resource_id", "last_frame_resource_id", "pose_resource_id", "reference_video_resource_id",
        "reference_audio_resource_id", "reference_resource_ids", "status", "production_settings",
    )
    body = {key: shot[key] for key in keys}; body["lock_version"] = shot["lock_version"]; body.update(changes); return body


def test_candidate_confirmation_duration_traceability_and_preserve_ready() -> None:
    init_db(); headers = _new_user(); stranger = _new_user("storyboard-other")
    project_id, _, scene_id, _, version_id = _project_scene(headers)
    candidate = client.post(f"/api/v2/short-drama/projects/{project_id}/scenes/{scene_id}/shot-candidates", headers=headers, json={"story_version_id": version_id})
    assert candidate.status_code == 201, candidate.text
    assert len(candidate.json()["payload"]["shots"]) == 3
    assert client.get(f"/api/v2/short-drama/projects/{project_id}/storyboard", headers=headers).json()["total_shots"] == 0
    confirmed = client.post(f"/api/v2/short-drama/projects/{project_id}/shot-candidates/{candidate.json()['id']}/confirm", headers=headers, json={"mode": "replace_drafts"})
    assert confirmed.status_code == 200, confirmed.text
    board = client.get(f"/api/v2/short-drama/projects/{project_id}/storyboard", headers=headers)
    assert board.status_code == 200; scene = board.json()["episodes"][0]["scenes"][0]; shots = scene["shots"]
    assert [item["shot_no"] for item in shots] == [1, 2, 3]
    assert all(item["source_story_version_id"] == version_id and item["status"] == "draft" for item in shots)
    assert abs(scene["shot_duration"] - scene["target_duration"]) < 0.01
    ready = client.put(f"/api/v2/short-drama/projects/{project_id}/shots/{shots[0]['id']}", headers=headers, json=_patch_body(shots[0], status="ready"))
    assert ready.status_code == 200, ready.text
    second = client.post(f"/api/v2/short-drama/projects/{project_id}/scenes/{scene_id}/shot-candidates", headers=headers, json={"story_version_id": version_id})
    assert any(item["code"] == "confirmed_preserved" for item in second.json()["validation_warnings"])
    assert client.post(f"/api/v2/short-drama/projects/{project_id}/shot-candidates/{second.json()['id']}/confirm", headers=headers, json={"mode": "replace_drafts"}).status_code == 200
    after = client.get(f"/api/v2/short-drama/projects/{project_id}/storyboard", headers=headers).json()["episodes"][0]["scenes"][0]["shots"]
    assert any(item["id"] == ready.json()["id"] and item["status"] == "ready" for item in after)
    assert [item["shot_no"] for item in after] == list(range(1, len(after)+1))
    assert client.get(f"/api/v2/short-drama/projects/{project_id}/storyboard", headers=stranger).status_code == 404


def test_copy_split_merge_reorder_bulk_and_continuous_numbers() -> None:
    init_db(); headers = _new_user("storyboard-edit"); project_id, _, scene_id, _, version_id = _project_scene(headers)
    candidate = client.post(f"/api/v2/short-drama/projects/{project_id}/scenes/{scene_id}/shot-candidates", headers=headers, json={"story_version_id": version_id}).json()
    client.post(f"/api/v2/short-drama/projects/{project_id}/shot-candidates/{candidate['id']}/confirm", headers=headers, json={"mode": "append"})
    shots = client.get(f"/api/v2/short-drama/projects/{project_id}/storyboard", headers=headers).json()["episodes"][0]["scenes"][0]["shots"]
    invalid_resource = client.put(f"/api/v2/short-drama/projects/{project_id}/shots/{shots[0]['id']}", headers=headers, json=_patch_body(shots[0], first_frame_resource_id=99999999))
    assert invalid_resource.status_code == 422
    copied = client.post(f"/api/v2/short-drama/projects/{project_id}/shots/{shots[0]['id']}/copy", headers=headers)
    assert copied.status_code == 201, copied.text
    split = client.post(f"/api/v2/short-drama/projects/{project_id}/shots/{copied.json()['id']}/split", headers=headers, json={"split_ratio": 0.4})
    assert split.status_code == 200, split.text; assert len(split.json()) == 2
    merged = client.post(f"/api/v2/short-drama/projects/{project_id}/shots/merge", headers=headers, json={"shot_ids": [item["id"] for item in split.json()]})
    assert merged.status_code == 200, merged.text
    current = client.get(f"/api/v2/short-drama/projects/{project_id}/storyboard", headers=headers).json()["episodes"][0]["scenes"][0]["shots"]
    reverse_ids = [item["id"] for item in reversed(current)]
    reordered = client.put(f"/api/v2/short-drama/projects/{project_id}/scenes/{scene_id}/shots/reorder", headers=headers, json={"shot_ids": reverse_ids})
    assert reordered.status_code == 200, reordered.text
    assert [item["id"] for item in reordered.json()] == reverse_ids
    assert [item["shot_no"] for item in reordered.json()] == list(range(1, len(current)+1))
    bulk = client.patch(f"/api/v2/short-drama/projects/{project_id}/shots/bulk", headers=headers, json={"shot_ids": reverse_ids[:2], "duration": 2.5, "aspect_ratio": "9:16", "quality_tier": "draft"})
    assert bulk.status_code == 200, bulk.text
    assert all(item["duration"] == 2.5 and item["production_settings"]["aspect_ratio"] == "9:16" for item in bulk.json())
    assert client.delete(f"/api/v2/short-drama/projects/{project_id}/shots/{reverse_ids[0]}", headers=headers).status_code == 200
    final = client.get(f"/api/v2/short-drama/projects/{project_id}/storyboard", headers=headers).json()["episodes"][0]["scenes"][0]["shots"]
    assert [item["shot_no"] for item in final] == list(range(1, len(final)+1))
