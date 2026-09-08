"""Machine-readable contract for the short-drama-director production engine.

The Markdown skill remains the authority.  This module exposes stable identifiers
used by prompts, imports and UI code so the product does not invent a second
director workflow.
"""
from __future__ import annotations

from typing import Any


SKILL_ID = "short-drama-director"
SKILL_VERSION = "6.5"
SCHEMA_VERSION = "2.0"

COMMANDS: tuple[dict[str, Any], ...] = (
    {"id": "screenplay", "command": "/写剧本", "engine": "five_gate_screenplay", "artifact": "script"},
    {"id": "dialogue_diagnosis", "command": "/台词诊断", "engine": "seven_dimension_three_part_rewrite"},
    {"id": "production_ledger", "command": "/剧组产出册", "engine": "production_ledger", "artifact": "production_ledger"},
    {"id": "asset_breakdown", "command": "/数字资产包", "engine": "sixteen_asset_lock_and_lineage", "artifact": "asset_requirements"},
    {"id": "asset_atlas", "command": "/资产图册", "engine": "asset_atlas_ssot", "artifact": "asset_atlas"},
    {"id": "emotion_curve", "command": "/情绪曲线", "engine": "twelve_beat_emotion_curve"},
    {"id": "character_asset_board", "command": "/角色资产板", "engine": "t1_t2_t3_lineage_images", "artifact": "character_asset_board"},
    {"id": "spatial_blocking", "command": "/顶视图", "engine": "topview_2x2_cam_axis", "artifact": "spatial_plan"},
    {"id": "storyboard", "command": "/做分镜", "engine": "dialogue_micro_expression_or_action_previs"},
    {"id": "speech_rate_check", "command": "/语速自检", "engine": "five_step_speech_rate_check"},
    {"id": "video_prompt", "command": "/生成视频提示词", "engine": "model_adapter_video_prompt", "artifact": "video_prompts"},
    {"id": "workflow_export", "command": "/导出工作流参数", "engine": "canvas_api_workflow_export", "artifact": "workflow_manifest"},
    {"id": "review", "command": "/审查", "engine": "p0_p1_p2_quality_gate"},
)

CAPABILITY_IDS = tuple(item["id"] for item in COMMANDS)

SKILL_MANIFEST: dict[str, Any] = {
    "skill_id": SKILL_ID,
    "skill_version": SKILL_VERSION,
    "schema_version": SCHEMA_VERSION,
    "commands": list(COMMANDS),
    "stages": ["P0_PROJECT_LOCK", "P1_SCREENPLAY", "P2_ASSET_PACKAGE", "P3_SPATIAL_STORYBOARD", "P4_VIDEO_PROMPTS", "P5_QUALITY"],
    "artifact_order": ["project_lock", "script", "production_ledger", "asset_requirements", "asset_atlas", "spatial_plan", "storyboard", "video_prompts", "quality_report"],
    "invariants": {
        "shot_unit": "one_group_one_shot_with_multiple_internal_cameras",
        "shot_internal_cameras": "timeline_storyboard_text",
        "max_planning_group_seconds": 15,
        "dialogue_format": "speaker_colon_text_one_line",
        "asset_grades": ["A", "B", "C"],
        "review_levels": ["P0", "P1", "P2"],
        "video_prompt_layers": ["director", "model_adapter", "execution"],
        "asset_first": True,
        "no_image_no_storyboard": True,
        "asset_atlas_is_ssot": True,
        "stable_key_prefixes": ["CHR", "AUD", "PRP", "SCN", "U"],
        "lineage_tiers": ["T1", "T2", "T3"],
        "camera_positions": ["CAM1", "CAM2", "CAM3", "CAM4"],
        "model_adapters": ["seedance_2_5", "seedance_2_0", "jimeng", "kling", "minimax_h3", "comfyui"],
        "video_prompt_checklist": ["render_time", "aspect_ratio", "camera_specs", "dialogue_and_micro_expression", "action_previs", "p0_p1_p2_review"],
    },
}


SCRIPT_MANIFEST_SYSTEM_PROMPT = (
    "你是 short-drama-director V6.5 Multi-Agent 漫剧导演引擎。严格执行 /写剧本 五阶门控、"
    "/台词诊断 七维检查、/数字资产包 与 /资产图册 的资产先行门禁、/做分镜 文武双模路由、/语速自检 五步流程、/生成视频提示词 模型适配和 /审查 P0/P1/P2 门禁。"
    "只输出一个合法 JSON 对象，不输出 Markdown 或思考过程。剧本是事实源，不得删改原始对白或虚构剧情事实。"
)

SCRIPT_MANIFEST_CONTRACT = (
    "按 Premise→Structure→Beat Sheet→Worldview & Entity Bounds→Professional Script Page 的顺序完成五阶门控，"
    "并在 gate_report 中逐阶给出 status、evidence、issues；先生成因果节拍 story_beats，再生成 scenes。"
    "一个 ◆组对应一个 shot；shot 可含多个内部镜头，但只能写入 timeline_storyboard 单字段，禁止 timeline_segments。"
    "每个 shot 必须包含稳定 external_key（U01-S01 递增）、shot_no、title、content、action、expression、dialogue、"
    "timeline_storyboard、continuity、shot_design_mode(dialogue/action/mixed)、action_intensity(R1/R2/R3或空)、"
    "shot_jobs、job_reason、reaction_pause、speech_rate_check、角色/场景/道具引用、时长和关键帧方案。"
    "对白逐句独占一行并使用‘角色名：对白’，旁白使用‘旁白：内容’，内心使用‘角色名（内心）：内容’。"
    "speech_rate_check 必须按拆句、计数、停顿预算、套档、速算、判定执行；P0 超时不得通过正式制作。"
    "文戏 timeline_storyboard 写六阶段微表情和反应流；武戏先定 R1/R2/R3，再写动力链 PREVIS、攻防状态、"
    "位移、接触、受力反馈和轴线。每个内部镜头至少承担改变情绪、推进动作、施加压力之一。"
    "角色只输出合并后的 identity、personality、appearance、asset_grade、identity_anchor、visual_prompt；"
    "场景只输出合并后的 description、spatial_snapshot、visual_prompt；道具输出 description、asset_grade、continuity_note、visual_prompt。"
    "完整图片提示词与业务描述分开，不得把提示词复制为 description。"
)


def skill_snapshot() -> dict[str, Any]:
    """Return a copy suitable for project settings and generation snapshots."""
    return {**SKILL_MANIFEST, "commands": [dict(item) for item in COMMANDS]}
