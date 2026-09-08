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


from app.short_drama.dialogue import extract_dialogue_lines, dialogue_metrics, dialogue_spans, total_duration

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
    "video_prompt": _object_schema(["prompt"], {"prompt": STRING}),
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
            if key not in value or value[key] is None:
                issues.append({"severity": "p1", "path": f"{path}.{key}", "message": f"AI 原始输出缺少字段：{key}",
                               "source": source, "actionable": False, "action_label": "人工复核"})
        for key, child in (schema.get("properties") or {}).items():
            if key in value:
                issues.extend(validate_schema(value[key], child, f"{path}.{key}", source=source))
    elif expected == "array" and schema.get("items"):
        for index, item in enumerate(value):
            issues.extend(validate_schema(item, schema["items"], f"{path}[{index}]", source=source))
    return issues


def _issue(severity: str, path: str, message: str, *, action: str | None = None,
           action_label: str = "人工复核", payload: dict[str, Any] | None = None,
           source: str = "director_rule") -> dict[str, Any]:
    return {"severity": severity, "path": path, "message": message, "source": source,
            "actionable": bool(action), "action": action, "action_label": action_label,
            "action_payload": payload or {}, "category": "creative", "blocking_stage": None}


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
            "load_bearing": None,
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
            for key in ("title", "purpose", "content", "shot_size", "camera_angle", "camera_movement",
                        "composition", "transition", "duration"):
                shot_source.setdefault(key, "ai" if shot.get(key) not in (None, "", []) else "system_default")
            content = str(shot.get("content") or "")
            dialogue = "\n".join(str(item.get("text") or "") for item in (shot.get("dialogue_lines") or [])
                                 if isinstance(item, dict) and str(item.get("text") or "").strip())
            if not dialogue:
                dialogue = "\n".join(line["text"] for line in extract_dialogue_lines(content))
            jobs = list(shot.get("shot_jobs") or [])
            shot["shot_jobs"] = jobs
            shot.setdefault("follow_target", "跟随画面主体的状态变化")
            shot.setdefault("eye_trace_in", "继承上一镜主要视觉落点")
            shot.setdefault("eye_trace_out", "落在下一镜核心信息出现区域")
            shot.setdefault("screen_direction", "保持当前动作轴同侧；越轴时使用中性镜头重建方位")
            shot.setdefault("reaction_pause", 0.0)
            shot.setdefault("continuity_state", "继承上一镜位置、动作、服装、道具和环境状态")
            shot.setdefault("audio_plan", {"dialogue": 0, "sfx": -6, "bgm": -16, "ducking": bool(dialogue)})
            duration = total_duration(float(shot.get("duration") or 0), shot)
            metrics = dialogue_metrics(dialogue, duration, float(shot.get("reaction_pause") or 0))
            shot["dialogue_metrics"] = metrics
            shot_issues: list[dict[str, Any]] = []
            if any(not line.get("speaker") for line in shot.get("dialogue_lines", [])):
                shot_issues.append(_issue("p1", f"{path}.dialogue_lines", "引号内文本已提取，但部分说话人无法可靠判断；请在原文标注“角色：台词”，并确认是否属于对白。"))
            if duration > 15:
                shot_issues.append(_issue("p0", f"{path}.duration", "建议将单个视频生成组控制在 15 秒内；当前仍允许继续操作。",
                    action="split_dialogue" if dialogue else None, action_label="预览拆镜" if dialogue else "人工重新规划", payload={"scene_index": si, "shot_index": hi}))
            if dialogue and metrics["status"] == "overtime":
                suggested = round(min(60.0, max(duration, metrics["required_seconds"])), 1)
                shot_issues.append(_issue("p0", f"{path}.content", f"对白与反应至少约需 {metrics['required_seconds']} 秒，超过当前总预算 {duration:g} 秒。",
                    action="set_duration", action_label=f"建议改为{suggested:g}秒", payload={"scene_index": si, "shot_index": hi, "duration": suggested if shot.get("timing_schema_version") == 2 else max(.1, suggested - float(shot.get("reaction_pause") or 0))}))
            if metrics["longest_sentence"] > 24:
                shot_issues.append(_issue("p1", f"{path}.content", f"最长句约 {metrics['longest_sentence']} 字，建议拆为正反打或反应镜头。",
                    action="split_dialogue", action_label="预览拆镜", payload={"scene_index": si, "shot_index": hi}))
            if not jobs or not str(shot.get("job_reason") or "").strip():
                shot_issues.append(_issue("p2", f"{path}.shot_jobs", "镜头任务尚未评估；请填写具体的信息、动作或情绪变化依据。"))
            if content and not shot.get("character_names"):
                shot_issues.append(_issue("p2", f"{path}.character_names", "镜头未标注出场角色，生成时无法注入角色一致性；空镜头可忽略。"))
            angle = f"{shot.get('camera_angle','')} {shot.get('composition','')}"
            if shot.get("shot_size") in {"中景", "全景"} and ("90" in angle or "正侧" in angle):
                shot_issues.append(_issue("p1", f"{path}.camera_angle", "中景/全景采用90°正侧拍可能削弱空间纵深。",
                    action="set_camera_angle", action_label="改为45°斜侧", payload={"scene_index": si, "shot_index": hi, "camera_angle": "45°斜侧平视"}))
            if any(word in content for word in EMPTY_ADJECTIVES):
                shot_issues.append(_issue("p2", f"{path}.content", "画面含空洞形容词，建议改写为肌肉、位移、光源或受力等可拍事实。"))
            if dialogue and metrics["characters"] <= 18 and float(shot.get("reaction_pause") or 0) <= 0:
                shot_issues.append(_issue("p2", f"{path}.reaction_pause", "对白后可预留0.3～0.8秒反应时间。",
                    action="add_reaction_pause", action_label="添加0.5秒反应", payload={"scene_index": si, "shot_index": hi, "reaction_pause": 0.5}))
            shot["qc_issues"] = shot_issues
            issues.extend(shot_issues)
    if abs(target_duration - 180) < 0.1 and not 14 <= len(all_shots) <= 15:
        issues.append(_issue("p1", "scenes.shots", f"180 秒成片建议规划 14～15 个生成组，当前为 {len(all_shots)} 组。",
            action_label="按叙事人工规划"))
    referenced = sorted({name for scene in scenes for name in (scene.get("character_names") or [])}
                        | {name for shot in all_shots for name in (shot.get("character_names") or [])})
    if referenced and not data.get("characters"):
        issues.append(_issue("p1", "characters", "场景与镜头引用了角色，但演员表为空；确认后将无法生成角色档案与一致性。",
            action="rebuild_cast", action_label="从引用重建演员表", payload={"names": referenced}))
    if not data.get("props") and any(shot.get("prop_names") for shot in all_shots):
        issues.append(_issue("p2", "props", "镜头引用了道具，但道具档案为空；可先补档或忽略。"))
    raw_meta["qc_summary"] = {level: sum(1 for item in issues if item.get("severity") == level) for level in ("p0", "p1", "p2")}
    raw_meta["all_rules_are_advisory"] = True
    return data, issues


def script_diagnostics(text: str, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = settings or {}; target = float(settings.get("target_duration") or 60)
    scene_count = len(re.findall(r"(?m)^\s*(?:#{1,3}\s*)?(?:场景|第?\s*\d+\s*场|\[场景)", text or ""))
    shot_count = len(re.findall(r"(?m)^\s*\[?分镜\s*\d+", text or ""))
    premise = (text or "").strip().splitlines()[0][:30] if text.strip() else ""
    dialogues: list[dict[str, Any]] = []
    suggestions: list[dict[str, Any]] = []
    for line in dialogue_spans(text):
        metrics = dialogue_metrics(line["text"], 15)
        dialogues.append({**line, "metrics": metrics, "scores": None, "assessment_status": "not_evaluated"})
        if metrics["longest_sentence"] > 24:
            suggestions.append(_issue("p1", f"lines[{line['line_index']}]", f"{line['speaker']}的最长句超过24字，建议在清单中预览拆镜，保留原文。"))
    gates = [
        {"gate": 1, "name": "核心前提与钩子", "status": "not_evaluated", "detail": "未评估：需分析主角欲望、阻碍、代价；不以首行文本代替前提"},
        {"gate": 2, "name": "三幕时长比例", "status": "not_evaluated", "detail": f"建议预算：铺垫 {target*.3:.0f}s / 冲突 {target*.5:.0f}s / 转折 {target*.2:.0f}s"},
        {"gate": 3, "name": "场景因果链", "status": "not_evaluated" if scene_count else "missing", "detail": f"识别到 {scene_count} 个场景、{shot_count} 个分镜标记"},
        {"gate": 4, "name": "人物动机与世界边界", "status": "not_evaluated", "detail": "建议确认时代、法律、技术/战力边界与关系利益方向"},
        {"gate": 5, "name": "排版与可拍摄性", "status": "not_evaluated" if shot_count else "missing", "detail": "建议使用场景、动作、对白和镜头备注的语义化格式"},
    ]
    if not premise:
        suggestions.append(_issue("p1", "premise", "建议先补充30字核心前提。", action="insert_premise_template", action_label="插入前提模板"))
    return {"gates": gates, "dialogues": dialogues, "suggestions": suggestions,
            "summary": {"scene_count": scene_count, "shot_count": shot_count, "dialogue_count": len(dialogues),
                        "suggestion_count": len(suggestions)}, "all_rules_are_advisory": True}
