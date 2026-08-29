"""Advisory director analysis for scripts and manifests.

Rules in this module never block saving, confirmation, or generation.  Each
finding declares whether the UI can apply a deterministic operation or needs
human review.
"""
from __future__ import annotations

import re
from copy import deepcopy
from math import ceil
from typing import Any


PRONOUNCEABLE = re.compile(r"[\u3400-\u9fffA-Za-z0-9]")
EMPTY_ADJECTIVES = ("很愤怒", "很压迫", "非常激烈", "史诗感", "速度极快", "剑法高超")


def _object_schema(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "required": required, "properties": properties}


STRING = {"type": "string"}
STRING_ARRAY = {"type": "array", "items": STRING}
OBJECT_ARRAY = {"type": "array", "items": {"type": "object"}}

AI_RESPONSE_SCHEMAS: dict[str, dict[str, Any]] = {
    "novel_chunk_analysis": _object_schema(
        ["synopsis", "premise", "characters", "locations", "events", "beats", "source_references"],
        {"synopsis": STRING, "premise": STRING, "opening_hook": STRING, "characters": OBJECT_ARRAY,
         "locations": OBJECT_ARRAY, "events": OBJECT_ARRAY, "beats": OBJECT_ARRAY,
         "relationship_graph": OBJECT_ARRAY, "worldview_bounds": {"type": "object"},
         "load_bearing_scenes": OBJECT_ARRAY, "continuity_facts": OBJECT_ARRAY,
         "adaptation_risks": OBJECT_ARRAY, "source_references": OBJECT_ARRAY},
    ),
    "novel_analysis_merge": _object_schema(
        ["synopsis", "premise", "structure", "beats", "characters", "locations", "events", "source_references"],
        {"synopsis": STRING, "premise": STRING, "opening_hook": STRING, "structure": {"type": "object"},
         "beats": OBJECT_ARRAY, "characters": OBJECT_ARRAY, "locations": OBJECT_ARRAY,
         "events": OBJECT_ARRAY, "relationship_graph": OBJECT_ARRAY, "worldview_bounds": {"type": "object"},
         "load_bearing_scenes": OBJECT_ARRAY, "continuity_facts": OBJECT_ARRAY,
         "adaptation_risks": OBJECT_ARRAY, "source_references": OBJECT_ARRAY},
    ),
    "novel_adaptation": _object_schema(["options"], {"options": OBJECT_ARRAY}),
    "episode_screenplay": _object_schema(
        ["title", "synopsis", "premise", "gate_report", "dialogue_diagnostics", "target_duration", "scenes"],
        {"title": STRING, "synopsis": STRING, "premise": STRING, "gate_report": {"type": "object"},
         "dialogue_diagnostics": OBJECT_ARRAY, "target_duration": {"type": "number"}, "scenes": OBJECT_ARRAY},
    ),
    "script_manifest": _object_schema(
        ["story_summary", "characters", "locations", "props", "scenes"],
        {"story_summary": STRING, "characters": OBJECT_ARRAY, "locations": OBJECT_ARRAY,
         "props": OBJECT_ARRAY, "scenes": OBJECT_ARRAY},
    ),
}


def validate_schema(value: Any, schema: dict[str, Any], path: str = "$", *, source: str = "raw_response") -> list[dict[str, Any]]:
    """Small JSON-Schema subset used as an advisory raw-response contract."""
    issues: list[dict[str, Any]] = []
    expected = schema.get("type")
    valid = {
        "object": isinstance(value, dict), "array": isinstance(value, list), "string": isinstance(value, str),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool), "boolean": isinstance(value, bool),
    }.get(expected, True)
    if not valid:
        return [{"severity": "p1", "path": path, "message": f"AI 原始输出应为 {expected}", "source": source,
                 "actionable": False, "action_label": "人工复核"}]
    if expected == "object":
        required = schema.get("required") or []
        for key in required:
            if key not in value or value[key] in (None, "", []):
                issues.append({"severity": "p1", "path": f"{path}.{key}", "message": f"AI 原始输出缺少字段：{key}",
                               "source": source, "actionable": False, "action_label": "人工复核"})
        for key, child in (schema.get("properties") or {}).items():
            if key in value:
                issues.extend(validate_schema(value[key], child, f"{path}.{key}", source=source))
    elif expected == "array" and schema.get("items"):
        for index, item in enumerate(value):
            issues.extend(validate_schema(item, schema["items"], f"{path}[{index}]", source=source))
    return issues


def dialogue_metrics(text: str, shot_duration: float) -> dict[str, Any]:
    spoken = len(PRONOUNCEABLE.findall(text or ""))
    punctuation = len(re.findall(r"[，、,]", text or "")) * 0.2 + len(re.findall(r"[。！？!?]", text or "")) * 0.45
    min_seconds = round(spoken / 5 + punctuation, 2) if spoken else 0
    max_seconds = round(spoken / 3.5 + punctuation, 2) if spoken else 0
    return {"characters": spoken, "speed_range": "3.5～5 字/秒", "min_seconds": min_seconds,
            "max_seconds": max_seconds, "shot_duration": shot_duration,
            "status": "overtime" if min_seconds > shot_duration else "long" if spoken > 24 else "ok"}


def _issue(severity: str, path: str, message: str, *, action: str | None = None,
           action_label: str = "人工复核", payload: dict[str, Any] | None = None,
           source: str = "director_rule") -> dict[str, Any]:
    return {"severity": severity, "path": path, "message": message, "source": source,
            "actionable": bool(action), "action": action, "action_label": action_label,
            "action_payload": payload or {}}


def enrich_manifest(content: dict[str, Any], target_duration: float = 0) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = deepcopy(content)
    issues: list[dict[str, Any]] = []
    raw_meta = data.setdefault("_analysis_meta", {})
    issues.extend(raw_meta.get("raw_validation_errors") or [])
    scenes = data.get("scenes") if isinstance(data.get("scenes"), list) else []
    all_shots: list[dict[str, Any]] = []
    for si, scene in enumerate(scenes):
        source = scene.setdefault("_field_sources", {})
        scene_defaults = {
            "scene_goal": scene.get("purpose") or "明确本场要改变的局面",
            "obstacle": "待导演确认主要阻碍", "escalation": "待导演确认升级行动",
            "reversal": "待导演确认转折", "outcome": "待导演确认新局面",
            "load_bearing": bool(scene.get("emotion") or len(scene.get("shots") or []) > 2),
            "environment_pressure": scene.get("atmosphere") or "待补充贯穿场次的物理环境压力",
            "screen_axis": "以主要角色视线连线为动作轴，画面左右以观众视角为准",
            "continuity_in": "继承上一场人物、服装、道具与空间状态",
            "continuity_out": "记录本场结束时人物位置、动作、服装、道具与环境状态",
        }
        for key, default in scene_defaults.items():
            if scene.get(key) in (None, "", []):
                scene[key] = default; source.setdefault(key, "system_default")
            else:
                source.setdefault(key, "ai")
        shots = scene.get("shots") if isinstance(scene.get("shots"), list) else []
        for hi, shot in enumerate(shots):
            all_shots.append(shot)
            path = f"scenes[{si}].shots[{hi}]"
            shot_source = shot.setdefault("_field_sources", {})
            for key in ("title", "purpose", "visual_description", "action", "expression", "dialogue", "narration",
                        "shot_size", "camera_angle", "camera_movement", "composition", "transition", "duration"):
                shot_source.setdefault(key, "ai" if shot.get(key) not in (None, "", []) else "system_default")
            jobs = list(shot.get("shot_jobs") or [])
            if not jobs:
                if shot.get("expression") or scene.get("emotion"): jobs.append("改变情绪")
                if shot.get("action"): jobs.append("推进动作")
                if shot.get("purpose") or scene.get("obstacle"): jobs.append("施加压力")
                shot["shot_jobs"] = jobs
                shot_source.setdefault("shot_jobs", "system_default")
            shot.setdefault("follow_target", "跟随画面主体的状态变化")
            shot.setdefault("eye_trace_in", "继承上一镜主要视觉落点")
            shot.setdefault("eye_trace_out", "落在下一镜核心信息出现区域")
            shot.setdefault("screen_direction", "保持当前动作轴同侧；越轴时使用中性镜头重建方位")
            shot.setdefault("reaction_pause", 0.0)
            shot.setdefault("continuity_state", "继承上一镜位置、动作、服装、道具和环境状态")
            shot.setdefault("audio_plan", {"dialogue": 0, "sfx": -6, "bgm": -16, "ducking": bool(shot.get("dialogue"))})
            duration = float(shot.get("duration") or 0)
            metrics = dialogue_metrics(str(shot.get("dialogue") or ""), duration)
            shot["dialogue_metrics"] = metrics
            shot_issues: list[dict[str, Any]] = []
            if duration > 15:
                shot_issues.append(_issue("p0", f"{path}.duration", "建议将单个视频生成组控制在 15 秒内；当前仍允许继续操作。",
                    action="set_duration", action_label="调整为15秒", payload={"scene_index": si, "shot_index": hi, "duration": 15}))
            if shot.get("dialogue") and metrics["status"] == "overtime":
                suggested = round(min(60.0, max(duration, metrics["min_seconds"] + 0.5)), 1)
                shot_issues.append(_issue("p0", f"{path}.dialogue", f"对白最快约需 {metrics['min_seconds']} 秒，超过当前镜头 {duration:g} 秒。",
                    action="set_duration", action_label=f"建议改为{suggested:g}秒", payload={"scene_index": si, "shot_index": hi, "duration": suggested}))
            if metrics["characters"] > 24:
                shot_issues.append(_issue("p1", f"{path}.dialogue", f"单句对白约 {metrics['characters']} 字，建议拆为正反打或反应镜头。",
                    action="split_dialogue", action_label="拆成两个镜头", payload={"scene_index": si, "shot_index": hi}))
            if not jobs:
                shot_issues.append(_issue("p1", f"{path}.shot_jobs", "镜头尚未承担情绪、动作或压力任务。",
                    action="set_shot_job", action_label="设为推进动作", payload={"scene_index": si, "shot_index": hi, "job": "推进动作"}))
            angle = f"{shot.get('camera_angle','')} {shot.get('composition','')}"
            if shot.get("shot_size") in {"中景", "全景"} and ("90" in angle or "正侧" in angle):
                shot_issues.append(_issue("p1", f"{path}.camera_angle", "中景/全景采用90°正侧拍可能削弱空间纵深。",
                    action="set_camera_angle", action_label="改为45°斜侧", payload={"scene_index": si, "shot_index": hi, "camera_angle": "45°斜侧平视"}))
            if any(word in str(shot.get("visual_description") or "") for word in EMPTY_ADJECTIVES):
                shot_issues.append(_issue("p2", f"{path}.visual_description", "画面含空洞形容词，建议改写为肌肉、位移、光源或受力等可拍事实。"))
            if shot.get("dialogue") and metrics["characters"] <= 18 and float(shot.get("reaction_pause") or 0) <= 0:
                shot_issues.append(_issue("p2", f"{path}.reaction_pause", "对白后可预留0.3～0.8秒反应时间。",
                    action="add_reaction_pause", action_label="添加0.5秒反应", payload={"scene_index": si, "shot_index": hi, "reaction_pause": 0.5}))
            shot["qc_issues"] = shot_issues
            issues.extend(shot_issues)
    if abs(target_duration - 180) < 0.1 and not 14 <= len(all_shots) <= 15:
        issues.append(_issue("p1", "scenes.shots", f"180 秒成片建议规划 14～15 个生成组，当前为 {len(all_shots)} 组。",
            action="normalize_group_count", action_label="自动规划15组", payload={"target_count": 15}))
    raw_meta["qc_summary"] = {level: sum(1 for item in issues if item.get("severity") == level) for level in ("p0", "p1", "p2")}
    raw_meta["all_rules_are_advisory"] = True
    return data, issues


def script_diagnostics(text: str, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = settings or {}; target = float(settings.get("target_duration") or 60)
    scene_count = len(re.findall(r"(?m)^\s*(?:#{1,3}\s*)?(?:场景|第?\s*\d+\s*场|\[场景)", text or ""))
    shot_count = len(re.findall(r"(?m)^\s*\[?分镜\s*\d+", text or ""))
    conflict = bool(re.search(r"阻止|必须|否则|危机|冲突|追杀|失败|代价|秘密|背叛", text or ""))
    premise = (text or "").strip().splitlines()[0][:30] if text.strip() else ""
    dialogues: list[dict[str, Any]] = []
    suggestions: list[dict[str, Any]] = []
    for line_index, line in enumerate((text or "").splitlines()):
        match = re.match(r"^\s*([\u3400-\u9fffA-Za-z0-9_·]{1,16})[：:]\s*[“\"]?(.+?)[”\"]?\s*$", line)
        if not match or match.group(1) in {"场景", "地点", "画面", "动作任务", "镜头备注", "对白"}: continue
        speaker, dialogue = match.group(1), match.group(2)
        metrics = dialogue_metrics(dialogue, 15)
        scores = {"voice_print": 3, "subtext": 3, "conflict_drive": 4 if conflict else 3,
                  "genre_voice": 3, "info_efficiency": 3, "rhythm": 2 if metrics["characters"] > 24 else 4,
                  "memorable_line": 3}
        card = {"line_index": line_index, "speaker": speaker, "text": dialogue, "metrics": metrics, "scores": scores}
        dialogues.append(card)
        if metrics["characters"] > 24:
            suggestions.append(_issue("p1", f"lines[{line_index}]", f"{speaker}的台词约{metrics['characters']}字，建议拆句并增加气口。",
                action="split_script_dialogue", action_label="自动拆句", payload={"line_index": line_index}))
    gates = [
        {"gate": 1, "name": "核心前提与钩子", "status": "review" if premise else "missing", "detail": premise or "尚未识别核心前提"},
        {"gate": 2, "name": "三幕时长比例", "status": "review", "detail": f"建议预算：铺垫 {target*.3:.0f}s / 冲突 {target*.5:.0f}s / 转折 {target*.2:.0f}s"},
        {"gate": 3, "name": "场景因果链", "status": "review" if scene_count else "missing", "detail": f"识别到 {scene_count} 个场景、{shot_count} 个分镜标记"},
        {"gate": 4, "name": "人物动机与世界边界", "status": "review", "detail": "建议确认时代、法律、技术/战力边界与关系利益方向"},
        {"gate": 5, "name": "排版与可拍摄性", "status": "review" if shot_count else "missing", "detail": "建议使用场景、动作、对白和镜头备注的语义化格式"},
    ]
    if not premise:
        suggestions.append(_issue("p1", "premise", "建议先补充30字核心前提。", action="insert_premise_template", action_label="插入前提模板"))
    return {"gates": gates, "dialogues": dialogues, "suggestions": suggestions,
            "summary": {"scene_count": scene_count, "shot_count": shot_count, "dialogue_count": len(dialogues),
                        "suggestion_count": len(suggestions)}, "all_rules_are_advisory": True}
