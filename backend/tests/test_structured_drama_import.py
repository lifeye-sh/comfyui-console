from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

from app.short_drama.structured_import_service import parse_content

CREATIONS = Path(__file__).parents[2] / "creations"
client = TestClient(app)


def _read(name: str) -> str:
    return (CREATIONS / name).read_text(encoding="utf-8")


def test_script_import_keeps_group_as_shot() -> None:
    result = parse_content("script", _read("小公主-300秒剧本.md"))
    assert result["counts"] == {"characters": 2, "scenes": 7, "shots": 24, "props": 6}
    assert [shot["shot_no"] for scene in result["scenes"] for shot in scene["shots"]] == list(range(1, 25))


def test_asset_import_preserves_all_seven_prompts_and_coverage() -> None:
    result = parse_content("assets", _read("小公主-资产参考图提示词.md"))
    assert result["counts"] == {"character_assets": 3, "location_assets": 4, "total": 7}
    by_key = {item["external_key"]: item for item in result["assets"]}
    assert by_key["A-2"]["coverage"] == list(range(1, 24))
    assert by_key["A-3"]["coverage"] == [24]
    assert by_key["S-2"]["coverage"] == [2]
    assert all(item["prompt"] for item in result["assets"])


def test_video_prompt_import_uses_one_timeline_field_per_shot() -> None:
    result = parse_content("video_prompts", _read("小公主-300秒-视频提示词.md"))
    assert result["counts"]["shots"] == 24
    assert result["counts"]["timeline_shots"] == 69
    assert result["counts"]["continuity"] == 24
    first = result["groups"][0]
    assert first["shot_no"] == 1
    assert first["duration"] == 12
    assert "[镜头1]" in first["timeline_storyboard"]
    assert "[镜头2]" in first["timeline_storyboard"]
    assert "timeline_segments" not in first


def _headers() -> dict[str, str]:
    admin = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"}).json()
    username = f"structured-{uuid4().hex[:10]}"
    created = client.post("/api/v1/users", json={"username": username, "password": "user12345", "role": "user"}, headers={"Authorization": f"Bearer {admin['access_token']}"})
    assert created.status_code == 201
    token = client.post("/api/v1/auth/login", json={"username": username, "password": "user12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_three_files_apply_in_order_and_keep_source() -> None:
    headers = _headers()
    created = client.post("/api/v2/short-drama/projects/quick-create", headers=headers, json={"name": "小公主", "source_type": "script", "episode_title": "第 1 集", "brief": {"aspect_ratio": "16:9", "episode_duration": 300}})
    assert created.status_code == 201, created.text
    project_id = created.json()["project"]["id"]
    base = f"/api/v2/short-drama/projects/{project_id}/structured-imports"
    cases = [("script", "小公主-300秒剧本.md"), ("assets", "小公主-资产参考图提示词.md"), ("video_prompts", "小公主-300秒-视频提示词.md")]
    for data_type, filename in cases:
        content = (CREATIONS / filename).read_bytes()
        preview = client.post(f"{base}/preview", headers=headers, data={"data_type": data_type}, files={"file": (filename, content, "text/markdown")})
        assert preview.status_code == 200, preview.text
        applied = client.post(f"{base}/apply", headers=headers, data={"data_type": data_type}, files={"file": (filename, content, "text/markdown")})
        assert applied.status_code == 201, applied.text
    imports = client.get(base, headers=headers)
    assert imports.status_code == 200
    assert [item["data_type"] for item in imports.json()] == ["script", "assets", "video_prompts"]
    assert all(len(item["checksum"]) == 64 and item["status"] == "applied" for item in imports.json())
    storyboard = client.get(f"/api/v2/short-drama/projects/{project_id}/storyboard", headers=headers)
    assert storyboard.status_code == 200, storyboard.text
    assert storyboard.json()["total_shots"] == 24
    shots = [shot for episode in storyboard.json()["episodes"] for scene in episode["scenes"] for shot in scene["shots"]]
    assert "[镜头1]" in shots[0]["timeline_storyboard"]
    assert shots[0]["continuity"]
    casting = client.get(f"/api/v2/short-drama/projects/{project_id}/casting", headers=headers)
    assert casting.status_code == 200
    assert len(casting.json()["asset_versions"]) == 7
