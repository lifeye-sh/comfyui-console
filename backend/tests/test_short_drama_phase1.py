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
    assert manifest["content"]["characters"][0]["stable_key"] == "CH-001"
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

    casting = client.get(f"/api/v2/short-drama/projects/{project_id}/casting", headers=headers)
    assert casting.status_code == 200, casting.text
    assert casting.json()["characters"][0]["name"] == "林不凡"
    assert casting.json()["characters"][0]["variants"][0]["name"] == "基础造型"
    character_prompt = casting.json()["characters"][0]["appearance"]
    assert character_prompt.splitlines() == [
        "1.Core Identity:人物外观待补充",
        "2.Facial Features:短发、清晰眉眼",
        "3.Hairstyle:黑色短发",
        "4.Clothing:蓝色睡衣",
        "5.Pose&Expression:白色背景，正面全身照",
        "6.Technical Quality:high-quality 3D CGI animation, 3d-animation, Pixar/DreamWorks style, subsurface scattering, detailed textures, stylized characters",
    ]
    assert "从本集剧本自动识别" not in character_prompt

    board = client.get(f"/api/v2/short-drama/projects/{project_id}/storyboard", headers=headers)
    assert board.status_code == 200, board.text
    assert board.json()["total_shots"] >= 2
    saved_shot = board.json()["episodes"][0]["scenes"][0]["shots"][0]
    assert saved_shot["expression"] == "惊慌"
    assert saved_shot["composition"] == "人物位于画面左侧三分线"
    assert saved_shot["production_settings"]["narration"] == "清晨，闹钟已经响过三次。"
    assert saved_shot["production_settings"]["manifest_prompt"]["effective"]["visual_style"] == "3D 动画电影风格"
