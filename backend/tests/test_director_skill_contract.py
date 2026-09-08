from app.short_drama.ai_service import PROMPTS
from app.short_drama.skill_contracts import CAPABILITY_IDS, SKILL_MANIFEST
from app.short_drama.structured_import_service import parse_content


def test_short_drama_director_registers_all_core_commands() -> None:
    assert SKILL_MANIFEST["skill_version"] == "6.5"
    for capability in (
        "screenplay", "dialogue_diagnosis", "production_ledger", "asset_breakdown",
        "asset_atlas", "emotion_curve", "character_asset_board", "spatial_blocking", "storyboard",
        "speech_rate_check", "video_prompt", "workflow_export", "review",
    ):
        assert capability in CAPABILITY_IDS
    assert SKILL_MANIFEST["invariants"]["shot_unit"] == "one_group_one_shot_with_multiple_internal_cameras"
    assert SKILL_MANIFEST["invariants"]["no_image_no_storyboard"] is True
    assert SKILL_MANIFEST["invariants"]["asset_atlas_is_ssot"] is True
    assert SKILL_MANIFEST["invariants"]["shot_internal_cameras"] == "timeline_storyboard_text"

def test_manifest_prompt_uses_skill_contract() -> None:
    name, system_prompt, user_prompt = PROMPTS["script_manifest"]
    assert name == "单集导演生产包"
    for value in ("五阶门控", "/台词诊断", "/做分镜", "/语速自检", "P0/P1/P2"):
        assert value in system_prompt
    for value in ("timeline_storyboard", "speech_rate_check", "shot_design_mode", "asset_grade"):
        assert value in user_prompt
    assert "禁止 timeline_segments" in user_prompt


def test_standard_dialogue_lines_remain_extractable() -> None:
    content = """# 《测试》
总时长 12s
### 5.2 角色
**@甲**（A 级）
成年人。
### 5.3 其他
### 场 1　内景 · 房间 - 日（0~12s · 1 组）
出场人物：@甲
◆组1
甲：你终于来了。
甲（内心）：不能让他看出来。
"""
    parsed = parse_content("script", content)
    shot = parsed["scenes"][0]["shots"][0]
    assert "甲：你终于来了。" in shot["content"]


def test_video_prompt_ai_contract_invokes_skill_and_uses_model_adapters() -> None:
    name, system_prompt, user_prompt = PROMPTS["video_prompt"]
    assert name == "漫剧视频提示词生成"
    assert "short-drama-director V6.5" in system_prompt
    assert "/生成视频提示词" in system_prompt
    for value in ("渲染时长", "画幅", "镜头规格", "minimax_h3", "Seedance"):
        assert value in user_prompt
    for value in ("【画幅风格】", "【场景资产】", "【核心人物】", "【负面排除】", "【时间轴分镜】", "【接续状态】", "picture_refs", "画面开始于首帧", "画面结束于尾帧"):
        assert value in user_prompt
    assert "detailed_description 只能保留【时间轴分镜】和【接续状态】" in user_prompt
