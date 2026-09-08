"""BigBanana 第一阶段纵向闭环。"""
from __future__ import annotations

from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _headers() -> dict[str, str]:
    admin = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"}).json()
    name = f"phase1-{uuid4().hex[:10]}"
    created = client.post("/api/v1/users", json={"username": name, "password": "user12345", "role": "user"}, headers={"Authorization": f"Bearer {admin['access_token']}"})
    assert created.status_code == 201
    token = client.post("/api/v1/auth/login", json={"username": name, "password": "user12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_quick_create_script_manifest_confirm_and_casting() -> None:
    headers = _headers()
    created = client.post("/api/v2/short-drama/projects/quick-create", headers=headers, json={
        "name": "迟到的清晨", "synopsis": "林不凡在卧室醒来并接到主管电话。", "source_type": "novel", "episode_title": "第 1 集",
        "brief": {"aspect_ratio": "16:9", "episode_duration": 60},
    })
    assert created.status_code == 201, created.text
    project_id, episode_id = created.json()["project"]["id"], created.json()["episode_id"]

    base = f"/api/v2/short-drama/projects/{project_id}"
    overview = client.get(f"{base}/overview", headers=headers)
    assert overview.status_code == 200, overview.text
    assert overview.json()["episode_count"] == 1
    assert overview.json()["scene_count"] == overview.json()["shot_count"] == 0
    screenplay = client.get(f"{base}/screenplay", headers=headers)
    assert screenplay.status_code == 200, screenplay.text
    assert screenplay.json()["episodes"][0]["id"] == episode_id
    assert screenplay.json()["episodes"][0]["number"] == 1
    empty_cast = client.get(f"{base}/casting", headers=headers)
    assert empty_cast.status_code == 200, empty_cast.text
    assert all(empty_cast.json()[key] == [] for key in ("characters", "locations", "props", "asset_versions"))

    script = client.get(f"/api/v2/short-drama/projects/{project_id}/episodes/{episode_id}/script", headers=headers).json()
    saved = client.patch(f"/api/v2/short-drama/projects/{project_id}/episodes/{episode_id}/script", headers=headers, json={
        "lock_version": script["lock_version"], "mode": "storyboard", "settings": {"target_duration": 60, "aspect_ratio": "16:9"},
        "text": "场景：林不凡家卧室（床边）\n\n[分镜 1]\n林不凡：完了，又要迟到了……\n林不凡从床上坐起。\n\n[分镜 2]\n手机在床头震动。",
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()["mode"] == "storyboard"

    generated = client.post(f"/api/v2/short-drama/projects/{project_id}/episodes/{episode_id}/manifests/generate", headers=headers, json={"idempotency_key": uuid4().hex})
    assert generated.status_code == 202, generated.text
    job = generated.json()
    assert job["status"] == "succeeded"
    manifests = client.get(f"/api/v2/short-drama/projects/{project_id}/episodes/{episode_id}/manifests", headers=headers).json()
    manifest = next(item for item in manifests if item["id"] == job["output_payload"]["manifest_id"])
    assert manifest["status"] == "draft" and manifest["content"]["scenes"][0]["shots"]
    assert manifest["content"]["story_summary"]
    assert manifest["content"]["characters"][0]["stable_key"] == "CHR-001"
    shot = manifest["content"]["scenes"][0]["shots"][0]
    assert set(shot["prompt"]["original"]) == {
        "base_visual", "visual_style", "camera_movement", "composition_guide",
        "initial_frame", "character_consistency", "negative_constraints",
    }

    manifest["content"]["characters"][0].update({
        "facial_features": "短发、清晰眉眼", "hairstyle": "黑色短发", "clothing": "蓝色睡衣",
        "visual_prompt": "林不凡，黑色短发，蓝色睡衣",
    })
    shot.update({"narration": "清晨，闹钟已经响过三次。", "expression": "惊慌", "composition": "人物位于画面左侧三分线"})
    manifest["content"]["props"] = [{"name": "Phone", "appearance": "Black phone"}]
    shot["prop_names"] = ["Phone", "Phone"]
    shot["character_names"] = [manifest["content"]["characters"][0]["name"]] * 2  # Duplicate AI annotations must not duplicate bindings.
    shot["prompt"]["override"] = {"visual_style": "3D 动画电影风格"}
    saved_manifest = client.patch(
        f"/api/v2/short-drama/projects/{project_id}/episodes/{episode_id}/manifests/{manifest['id']}",
        headers=headers,
        json={"lock_version": manifest["lock_version"], "content": manifest["content"]},
    )
    assert saved_manifest.status_code == 200, saved_manifest.text
    manifest = saved_manifest.json()
    assert manifest["content"]["scenes"][0]["shots"][0]["prompt"]["effective"]["visual_style"] == "3D 动画电影风格"

    confirmed = client.post(f"/api/v2/short-drama/projects/{project_id}/episodes/{episode_id}/manifests/{manifest['id']}/confirm", headers=headers)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"

    pipeline = client.get(f"{base}/episodes/{episode_id}/pipeline", headers=headers)
    assert pipeline.status_code == 200, pipeline.text
    assert pipeline.json()["skill"]["skill_version"] == "6.5"
    assert pipeline.json()["pending_assets"]
    blocked = client.post(f"{base}/episodes/{episode_id}/asset-atlas/confirm", headers=headers)
    assert blocked.status_code == 409

    casting = client.get(f"/api/v2/short-drama/projects/{project_id}/casting", headers=headers)
    assert casting.status_code == 200, casting.text
    assert casting.json()["characters"][0]["name"] == "林不凡"
    assert casting.json()["characters"][0]["variants"][0]["name"] == "基础造型"
    character = casting.json()["characters"][0]
    assert character["appearance"] == "人物外观待补充"
    assert character["variants"][0]["description"] == "蓝色睡衣"
    asset_prompts = [item for item in casting.json()["asset_versions"] if item["entity_type"] == "character"]
    assert asset_prompts and asset_prompts[0]["prompt"] == "林不凡，黑色短发，蓝色睡衣"

    board = client.get(f"/api/v2/short-drama/projects/{project_id}/storyboard", headers=headers)
    assert board.status_code == 200, board.text
    assert board.json()["total_shots"] >= 2
    saved_shot = board.json()["episodes"][0]["scenes"][0]["shots"][0]
    assert saved_shot["expression"] == "惊慌"
    assert saved_shot["composition"] == "人物位于画面左侧三分线"
    assert saved_shot["production_settings"]["narration"] == "清晨，闹钟已经响过三次。"
    assert saved_shot["production_settings"]["manifest_prompt"]["effective"]["visual_style"] == "3D 动画电影风格"
    # The confirmed downstream shot must use the post-analysis manifest, including derived dialogue.
    expected_dialogues = []
    for source_scene in confirmed.json()["content"]["scenes"]:
        for source_shot in source_scene["shots"]:
            expected_dialogues.append("\n".join(f"{x['speaker']}：{x['text']}" if x.get("speaker") else x["text"] for x in source_shot["dialogue_lines"]))
    actual_dialogues = []
    for target_scene in board.json()["episodes"][0]["scenes"]:
        for target_shot in target_scene["shots"]:
            actual_dialogues.append(target_shot["dialogue"] or "\n".join(f"{x['speaker']}：{x['text']}" if x.get("speaker") else x["text"] for x in target_shot["production_settings"]["dialogue_lines"]))
    assert any(expected_dialogues) and actual_dialogues == expected_dialogues

    base = f"/api/v2/short-drama/projects/{project_id}"
    overview = client.get(f"{base}/overview", headers=headers)
    assert overview.status_code == 200, overview.text
    assert overview.json()["episode_count"] == 1
    assert overview.json()["scene_count"] == 1
    assert overview.json()["shot_count"] == board.json()["total_shots"]
    assert len(casting.json()["characters"]) == 1
    assert len(casting.json()["locations"]) == 1
    assert [item["name"] for item in casting.json()["props"]] == ["Phone"]
    assert len(saved_shot["prop_ids"]) == 1
    assert len(saved_shot["character_ids"]) == 1

    manifest_url = f"{base}/episodes/{episode_id}/manifests/{manifest['id']}"
    unlocked = client.post(f"{manifest_url}/unlock", headers=headers)
    assert unlocked.status_code == 200, unlocked.text
    reviewed = client.post(f"{manifest_url}/review", headers=headers)
    assert reviewed.status_code == 200, reviewed.text
    reconfirmed = client.post(f"{manifest_url}/confirm", headers=headers)
    assert reconfirmed.status_code == 200, reconfirmed.text
    repeat = client.post(f"{manifest_url}/confirm", headers=headers)
    assert repeat.status_code == 200, repeat.text
    after = client.get(f"{base}/casting", headers=headers).json()
    assert [item["id"] for item in after["characters"]] == [item["id"] for item in casting.json()["characters"]]
    assert len(after["characters"][0]["variants"]) == 1
    assert len(after["locations"]) == len(after["props"]) == 1
    assert client.get(f"{base}/overview", headers=headers).json()["shot_count"] == board.json()["total_shots"]

    from app.db import SessionLocal
    from app.short_drama.phase1_service import create_asset_version
    with SessionLocal() as db:
        asset = create_asset_version(db, created.json()["project"]["owner_id"], project_id,
            "character", after["characters"][0]["id"], resource_id=None, source_task_id=None,
            prompt="Acceptance candidate", generation_snapshot={})
        assert asset.created_at and asset.updated_at
    versions = client.get(f"{base}/casting", headers=headers).json()["asset_versions"]
    assert len(versions) == 2
    assert {item["entity_type"] for item in versions} == {"character"}
    assert versions[0]["prompt"] == "Acceptance candidate"
    assert any(item["prompt"] == "Acceptance candidate" for item in versions)
    assert any(
        item["generation_snapshot"].get("purpose") == "skill_asset_prompt"
        for item in versions
    )


def test_migrated_application_lifespan():
    # Exercise real startup/seeding and shutdown against the migrated test database.
    with TestClient(app) as running:
        login = running.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
        assert login.status_code == 200, login.text
