from app.services.video_rules import duration_errors
from app.short_drama.phase1_service import _analyze_manifest


def test_video_duration_over_fifteen_seconds_returns_advice() -> None:
    assert duration_errors("video", {"duration": 15}) == []
    messages = duration_errors("video", {"duration": 15.1})
    assert len(messages) == 1 and "建议" in messages[0] and "不影响继续生成" in messages[0]


def test_non_video_generation_is_not_affected() -> None:
    assert duration_errors("image", {"duration": 60}) == []


def test_180_second_manifest_suggests_fourteen_or_fifteen_groups() -> None:
    def shot(index: int, duration: float = 12) -> dict:
        return {
            "shot_no": str(index), "visual_description": f"画面 {index}", "duration": duration,
            "character_names": [], "prop_names": [], "prompt": {"original": {}},
        }

    content = {
        "story_summary": "测试故事", "characters": [], "props": [],
        "locations": [{"name": "测试场景"}],
        "scenes": [{
            "scene_no": "1", "location_name": "测试场景", "rhythm": "递进", "emotion": "紧张",
            "shots": [shot(index) for index in range(1, 14)],
        }],
    }
    _, issues = _analyze_manifest(content, 180)
    assert any(issue["severity"] in {"p0", "p1", "p2"} and "14～15" in issue["message"] for issue in issues)
    assert not any(issue["severity"] == "blocker" for issue in issues)

    content["scenes"][0]["shots"] = [shot(index, 180 / 15) for index in range(1, 16)]
    _, issues = _analyze_manifest(content, 180)
    assert not any(issue["severity"] == "blocker" for issue in issues)


def test_manifest_advises_on_a_generation_group_over_fifteen_seconds() -> None:
    content = {
        "story_summary": "测试故事", "characters": [], "props": [],
        "locations": [{"name": "测试场景"}],
        "scenes": [{
            "scene_no": "1", "location_name": "测试场景", "rhythm": "递进", "emotion": "紧张",
            "shots": [{"shot_no": "1", "visual_description": "长镜头", "duration": 16, "character_names": [], "prop_names": [], "prompt": {"original": {}}}],
        }],
    }
    _, issues = _analyze_manifest(content, 60)
    assert any(issue["severity"] == "p0" and "15 秒" in issue["message"] for issue in issues)
    assert not any(issue["severity"] == "blocker" for issue in issues)
