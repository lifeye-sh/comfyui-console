"""BigBanana 第一阶段的单集剧本、拍摄清单和素材版本闭环。"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Character, CharacterVariant, Episode, Location, ProjectAssetVersion, Prop, Scene,
    ScriptManifestVersion, Shot, ShotCharacterBinding, ShortDramaProject,
)
from app.schemas.short_drama import ProjectCreateIn, ProjectQuickCreateIn
from app.short_drama import project_service
from app.short_drama.director_rules import enrich_manifest, script_diagnostics


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _episode(db: Session, owner_id: int, project_id: int, episode_id: int) -> Episode:
    project_service.owned_project(db, owner_id, project_id)
    item = db.query(Episode).filter(Episode.id == episode_id, Episode.project_id == project_id, Episode.owner_id == owner_id).first()
    if not item:
        raise project_service.ProjectNotFoundError("分集不存在")
    return item


def quick_create(db: Session, owner_id: int, body: ProjectQuickCreateIn) -> tuple[ShortDramaProject, Episode]:
    project = project_service.create_project(db, owner_id, ProjectCreateIn(**body.model_dump(exclude={"episode_title"})))
    episode = Episode(
        owner_id=owner_id, project_id=project.id, number=1, sort_order=0,
        title=body.episode_title.strip(), target_duration=body.brief.episode_duration,
        script_settings={"language": "zh-CN", "aspect_ratio": body.brief.aspect_ratio, "target_duration": body.brief.episode_duration},
    )
    db.add(episode)
    project.stage = "script"
    db.commit(); db.refresh(project); db.refresh(episode)
    return project, episode


def get_script(db: Session, owner_id: int, project_id: int, episode_id: int) -> dict[str, Any]:
    item = _episode(db, owner_id, project_id, episode_id)
    return {"episode_id": item.id, "project_id": item.project_id, "title": item.title, "mode": item.script_mode,
            "text": item.script_text, "settings": item.script_settings or {}, "script_revision": item.script_revision,
            "lock_version": item.lock_version, "updated_at": item.updated_at,
            "diagnostics": script_diagnostics(item.script_text, item.script_settings or {})}


def update_script(db: Session, owner_id: int, project_id: int, episode_id: int, *, lock_version: int, mode: str, text: str, settings: dict[str, Any]) -> dict[str, Any]:
    item = _episode(db, owner_id, project_id, episode_id)
    if item.lock_version != lock_version:
        raise project_service.ProjectConflictError("剧本已在其他窗口修改，请刷新后重试")
    item.script_mode = mode; item.script_text = text; item.script_settings = settings
    item.script_revision += 1; item.lock_version += 1
    db.commit(); db.refresh(item)
    return get_script(db, owner_id, project_id, episode_id)


def _speaker(line: str) -> str | None:
    match = re.match(r"^([\u4e00-\u9fa5A-Za-z0-9_·]{1,12})[：:]", line.strip())
    name = match.group(1) if match else None
    return None if name in {"场景", "地点", "时间", "画面", "动作任务", "镜头备注", "对话"} else name


PROMPT_SEGMENTS = (
    "base_visual", "visual_style", "camera_movement", "composition_guide",
    "initial_frame", "character_consistency", "negative_constraints",
)

DEFAULT_CHARACTER_POSE = "白色背景，正面全身照"
DEFAULT_CHARACTER_TECHNICAL = (
    "high-quality 3D CGI animation, 3d-animation, Pixar/DreamWorks style, "
    "subsurface scattering, detailed textures, stylized characters"
)


def _text(value: Any, default: str = "") -> str:
    return str(value).strip() if value is not None else default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _entity_objects(value: Any, prefix: str) -> list[dict[str, Any]]:
    """Accept imperfect model output while preserving a stable object contract."""
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(value, 1):
        data = dict(raw) if isinstance(raw, dict) else {"name": _text(raw)}
        if not _text(data.get("name")):
            continue
        data["name"] = _text(data["name"])
        data["stable_key"] = _text(data.get("stable_key")) or f"{prefix}-{index:03d}"
        result.append(data)
    return result


def _character_visual_prompt(character: dict[str, Any]) -> str:
    """Compile the only six image-generation attributes allowed on a character card."""
    fields = (
        ("1.Core Identity", _text(character.get("core_identity")) or _text(character.get("identity"))),
        ("2.Facial Features", _text(character.get("facial_features"))),
        ("3.Hairstyle", _text(character.get("hairstyle"))),
        ("4.Clothing", _text(character.get("clothing"))),
        ("5.Pose&Expression", _text(character.get("pose_expression")) or DEFAULT_CHARACTER_POSE),
        ("6.Technical Quality", _text(character.get("technical_style")) or DEFAULT_CHARACTER_TECHNICAL),
    )
    return "\n".join(f"{label}:{value}" for label, value in fields)


def _prompt_bundle(shot: dict[str, Any]) -> dict[str, dict[str, str]]:
    raw = shot.get("prompt") if isinstance(shot.get("prompt"), dict) else {}
    original_raw = raw.get("original") if isinstance(raw.get("original"), dict) else {}
    override_raw = raw.get("override") if isinstance(raw.get("override"), dict) else {}
    effective_raw = raw.get("effective") if isinstance(raw.get("effective"), dict) else {}
    defaults = {
        "base_visual": _text(original_raw.get("base_visual") or shot.get("visual_description")),
        "visual_style": _text(original_raw.get("visual_style") or shot.get("mood")),
        "camera_movement": _text(original_raw.get("camera_movement") or shot.get("camera_movement")),
        "composition_guide": _text(original_raw.get("composition_guide") or shot.get("composition")),
        "initial_frame": _text(original_raw.get("initial_frame")),
        "character_consistency": _text(original_raw.get("character_consistency")),
        "negative_constraints": _text(original_raw.get("negative_constraints")),
    }
    original = {key: _text(original_raw.get(key)) or defaults[key] for key in PROMPT_SEGMENTS}
    override = {key: _text(override_raw.get(key)) for key in PROMPT_SEGMENTS if _text(override_raw.get(key))}
    effective = {
        key: _text(effective_raw.get(key)) or override.get(key) or original[key]
        for key in PROMPT_SEGMENTS
    }
    return {"original": original, "override": override, "effective": effective}


def _normalize_manifest(content: dict[str, Any], episode: Episode) -> dict[str, Any]:
    data = dict(content) if isinstance(content, dict) else {}
    characters = _entity_objects(data.get("characters"), "CH")
    locations = _entity_objects(data.get("locations"), "LOC")
    props = _entity_objects(data.get("props"), "PROP")

    for character in characters:
        for key in ("gender", "identity", "age_appearance", "core_identity", "facial_features", "hairstyle",
                    "clothing", "pose_expression", "technical_style", "negative_constraints", "description", "visual_prompt"):
            character[key] = _text(character.get(key))
        character["description"] = character["description"] or character.get("appearance", "")
        character["core_identity"] = character["core_identity"] or character["identity"]
        character["pose_expression"] = character["pose_expression"] or DEFAULT_CHARACTER_POSE
        character["technical_style"] = character["technical_style"] or DEFAULT_CHARACTER_TECHNICAL
        character["visual_prompt"] = _character_visual_prompt(character)
    for location in locations:
        for key in ("description", "spatial_layout", "time_weather", "lighting", "visual_prompt"):
            location[key] = _text(location.get(key))
        location["sub_locations"] = _strings(location.get("sub_locations"))
        location["color_palette"] = _strings(location.get("color_palette"))
        location["fixed_objects"] = _strings(location.get("fixed_objects"))
    for prop in props:
        for key in ("category", "description", "appearance", "owner_character_name", "appearance_scope", "continuity_note", "visual_prompt"):
            prop[key] = _text(prop.get(key))
        prop["critical"] = bool(prop.get("critical", False))

    scenes: list[dict[str, Any]] = []
    raw_scenes = data.get("scenes") if isinstance(data.get("scenes"), list) else []
    for scene_index, raw_scene in enumerate(raw_scenes, 1):
        scene = dict(raw_scene) if isinstance(raw_scene, dict) else {}
        scene["scene_no"] = _text(scene.get("scene_no")) or str(scene_index)
        for key in ("heading", "location_name", "sub_location", "time_of_day", "interior_exterior",
                    "rhythm", "emotion", "atmosphere", "content"):
            scene[key] = _text(scene.get(key))
        scene["location_name"] = scene["location_name"] or scene["heading"] or "待确认场景"
        scene["heading"] = scene["heading"] or scene["location_name"]
        scene["character_names"] = _strings(scene.get("character_names"))
        scene["prop_names"] = _strings(scene.get("prop_names"))
        shots: list[dict[str, Any]] = []
        raw_shots = scene.get("shots") if isinstance(scene.get("shots"), list) else []
        for shot_index, raw_shot in enumerate(raw_shots, 1):
            shot = dict(raw_shot) if isinstance(raw_shot, dict) else {}
            shot["shot_no"] = _text(shot.get("shot_no")) or str(shot_index)
            for key in ("title", "purpose", "visual_description", "action", "expression", "dialogue", "narration",
                        "inner_monologue", "mood", "shot_size", "camera_angle", "camera_movement", "composition", "transition"):
                shot[key] = _text(shot.get(key))
            shot["title"] = shot["title"] or f"镜头 {shot['shot_no']}"
            shot["shot_size"] = shot["shot_size"] or "中景"
            shot["camera_angle"] = shot["camera_angle"] or "平视"
            shot["camera_movement"] = shot["camera_movement"] or "固定"
            shot["duration"] = max(0.1, _float(shot.get("duration"), 3.0))
            shot["character_names"] = _strings(shot.get("character_names"))
            shot["prop_names"] = _strings(shot.get("prop_names"))
            shot["prompt"] = _prompt_bundle(shot)
            shots.append(shot)
        scene["shots"] = shots
        if not scene["character_names"]:
            scene["character_names"] = sorted({name for shot in shots for name in shot["character_names"]})
        if not scene["prop_names"]:
            scene["prop_names"] = sorted({name for shot in shots for name in shot["prop_names"]})
        scenes.append(scene)
    return {
        "story_summary": _text(data.get("story_summary")) or _text(data.get("synopsis")) or episode.script_text[:1000],
        "characters": characters, "locations": locations, "props": props, "scenes": scenes,
    }


def _validate_manifest(content: dict[str, Any], target_duration: float = 0) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    scenes = content.get("scenes", [])
    if not scenes:
        return [{"severity": "p0", "path": "scenes", "message": "建议至少补充一个场景", "source": "manifest_check",
                 "actionable": False, "action_label": "人工补充"}]
    if not _text(content.get("story_summary")):
        issues.append({"severity": "warning", "path": "story_summary", "message": "缺少本集故事梗概"})
    scene_numbers: set[str] = set()
    character_items = content.get("characters", [])
    location_items = content.get("locations", [])
    prop_items = content.get("props", [])
    character_names = {item["name"] for item in character_items}
    location_names = {item["name"] for item in location_items}
    prop_names = {item["name"] for item in prop_items}
    if len(character_names) != len(character_items):
        issues.append({"severity": "blocker", "path": "characters", "message": "演员表存在重名项"})
    if len(location_names) != len(location_items):
        issues.append({"severity": "blocker", "path": "locations", "message": "场景档案存在重名项"})
    for ci, character in enumerate(character_items):
        missing = [label for field, label in (("identity", "身份"), ("facial_features", "面部特征"),
                   ("hairstyle", "发型"), ("clothing", "服装"), ("visual_prompt", "角色提示词")) if not _text(character.get(field))]
        if missing:
            issues.append({"severity": "warning", "path": f"characters[{ci}]", "message": f"角色“{character['name']}”缺少：{'、'.join(missing)}"})
    for si, scene in enumerate(scenes):
        prefix = f"scenes[{si}]"
        if scene["scene_no"] in scene_numbers:
            issues.append({"severity": "blocker", "path": f"{prefix}.scene_no", "message": "场号重复"})
        scene_numbers.add(scene["scene_no"])
        if not scene["location_name"]:
            issues.append({"severity": "blocker", "path": f"{prefix}.location_name", "message": "缺少场景名称"})
        elif scene["location_name"] not in location_names:
            issues.append({"severity": "warning", "path": f"{prefix}.location_name", "message": "场景未建立完整环境档案"})
        if not scene["shots"]:
            issues.append({"severity": "blocker", "path": f"{prefix}.shots", "message": "场景至少需要一个镜头"})
        if not scene["rhythm"] or not scene["emotion"]:
            issues.append({"severity": "warning", "path": prefix, "message": "场次缺少节奏或核心情绪分析"})
        shot_numbers: set[str] = set()
        for hi, shot in enumerate(scene["shots"]):
            shot_prefix = f"{prefix}.shots[{hi}]"
            if shot["shot_no"] in shot_numbers:
                issues.append({"severity": "blocker", "path": f"{shot_prefix}.shot_no", "message": "镜号重复"})
            shot_numbers.add(shot["shot_no"])
            if not shot["visual_description"]:
                issues.append({"severity": "blocker", "path": f"{shot_prefix}.visual_description", "message": "缺少画面叙事"})
            prompt_original = shot.get("prompt", {}).get("original", {})
            missing_prompt = [label for field, label in (("visual_style", "视觉风格"), ("composition_guide", "构图指导"),
                              ("initial_frame", "起始帧"), ("character_consistency", "角色一致性"),
                              ("negative_constraints", "负面约束")) if not _text(prompt_original.get(field))]
            if missing_prompt:
                issues.append({"severity": "warning", "path": f"{shot_prefix}.prompt", "message": f"镜头生成提示词缺少：{'、'.join(missing_prompt)}"})
            for name in shot["character_names"]:
                if name not in character_names:
                    issues.append({"severity": "blocker", "path": f"{shot_prefix}.character_names", "message": f"角色“{name}”没有演员档案"})
            for name in shot["prop_names"]:
                if name not in prop_names:
                    issues.append({"severity": "warning", "path": f"{shot_prefix}.prop_names", "message": f"道具“{name}”没有道具档案"})
    all_shots = [shot for scene in scenes for shot in scene["shots"]]
    total = sum(shot["duration"] for shot in all_shots)
    if target_duration and abs(total - target_duration) > max(5, target_duration * 0.2):
        issues.append({"severity": "warning", "path": "total_duration", "message": f"镜头总时长 {total:.1f} 秒与目标 {target_duration:.1f} 秒偏差较大"})
    # 兼容旧校验器，但所有结果都只是提示。p0/p1/p2 仅表示处理优先级，永不阻断操作。
    normalized: list[dict[str, Any]] = []
    for issue in issues:
        item = dict(issue)
        item["severity"] = {"blocker": "p0", "warning": "p1"}.get(str(item.get("severity")), item.get("severity", "p2"))
        item.setdefault("source", "manifest_check")
        item.setdefault("actionable", False)
        item.setdefault("action_label", "人工复核")
        normalized.append(item)
    return normalized


def _analyze_manifest(content: dict[str, Any], target_duration: float) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    enriched, director_issues = enrich_manifest(content, target_duration)
    return enriched, _validate_manifest(enriched, target_duration) + director_issues


def _build_manifest(item: Episode) -> dict[str, Any]:
    text = item.script_text.strip()
    chunks = [part.strip() for part in re.split(r"\n\s*\n|(?=\[?分镜\s*\d+\]?)", text) if part.strip()]
    if not chunks:
        chunks = ["请补充剧本内容"]
    characters = sorted({name for chunk in chunks for line in chunk.splitlines() if (name := _speaker(line))})
    location = "待确认场景"
    heading = re.search(r"(?:场景|地点)[：:]\s*([^\n]+)", text)
    if heading:
        location = heading.group(1).strip()[:160]
    shots: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks, 1):
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        dialogue = "\n".join(line for line in lines if _speaker(line))
        visual = " ".join(line for line in lines if not _speaker(line)) or chunk
        shots.append({"shot_no": index, "title": f"镜头 {index}", "purpose": "推进当前叙事", "visual_description": visual[:2000], "action": visual[:1000],
                      "dialogue": dialogue[:2000], "shot_size": "中景", "camera_angle": "平视",
                      "camera_movement": "固定", "duration": max(2.0, min(8.0, len(chunk) / 18)),
                      "character_names": sorted({n for line in lines if (n := _speaker(line))}), "prop_names": []})
    return _normalize_manifest({"story_summary": text[:1000], "scenes": [{"scene_no": "1", "heading": location, "location_name": location,
                         "time_of_day": "", "interior_exterior": "", "content": text, "shots": shots}],
            "characters": [{"name": name, "identity": "从本集剧本自动识别", "core_identity": "人物外观待补充"} for name in characters],
            "locations": [{"name": location, "description": "从本集剧本自动识别的场景环境"}], "props": []}, item)


def generate_manifest(db: Session, owner_id: int, project_id: int, episode_id: int, ai_content: dict[str, Any] | None = None) -> ScriptManifestVersion:
    item = _episode(db, owner_id, project_id, episode_id)
    if not item.script_text.strip():
        raise project_service.ProjectConflictError("请先填写并保存剧本内容")
    version = int(db.query(func.max(ScriptManifestVersion.version)).filter(ScriptManifestVersion.episode_id == item.id).scalar() or 0) + 1
    content = _normalize_manifest(ai_content, item) if ai_content is not None else _build_manifest(item)
    if not content.get("scenes"):
        raise project_service.ProjectConflictError("AI 未返回有效的场景与镜头清单")
    target_duration = _float((item.script_settings or {}).get("target_duration") or item.target_duration)
    content, validation_errors = _analyze_manifest(content, target_duration)
    total = sum(shot["duration"] for scene in content["scenes"] for shot in scene["shots"])
    manifest = ScriptManifestVersion(owner_id=owner_id, project_id=project_id, episode_id=item.id, version=version,
        source_script_revision=item.script_revision, mode=item.script_mode, summary=f"AI 已分析 {len(content['scenes'])} 个场景、{sum(len(x['shots']) for x in content['scenes'])} 个镜头",
        total_duration=total, content=content, validation_errors=validation_errors)
    db.add(manifest); db.commit(); db.refresh(manifest)
    return manifest


def list_manifests(db: Session, owner_id: int, project_id: int, episode_id: int) -> list[ScriptManifestVersion]:
    episode = _episode(db, owner_id, project_id, episode_id)
    items = db.query(ScriptManifestVersion).filter(ScriptManifestVersion.owner_id == owner_id, ScriptManifestVersion.episode_id == episode_id).order_by(ScriptManifestVersion.version.desc()).all()
    target_duration = _float((episode.script_settings or {}).get("target_duration") or episode.target_duration)
    changed = False
    for item in items:
        normalized = _normalize_manifest(item.content or {}, episode)
        normalized, issues = _analyze_manifest(normalized, target_duration)
        total = sum(shot["duration"] for scene in normalized["scenes"] for shot in scene["shots"])
        if normalized != item.content or issues != item.validation_errors or total != item.total_duration:
            item.content = normalized; item.validation_errors = issues; item.total_duration = total; changed = True
    if changed:
        db.commit()
        for item in items: db.refresh(item)
    return items


def owned_manifest(db: Session, owner_id: int, project_id: int, episode_id: int, manifest_id: int) -> ScriptManifestVersion:
    _episode(db, owner_id, project_id, episode_id)
    item = db.query(ScriptManifestVersion).filter(ScriptManifestVersion.id == manifest_id, ScriptManifestVersion.owner_id == owner_id,
        ScriptManifestVersion.project_id == project_id, ScriptManifestVersion.episode_id == episode_id).first()
    if not item: raise project_service.ProjectNotFoundError("拍摄清单不存在")
    return item


def patch_manifest(db: Session, owner_id: int, project_id: int, episode_id: int, manifest_id: int, *, lock_version: int, summary: str | None, content: dict[str, Any] | None) -> ScriptManifestVersion:
    item = owned_manifest(db, owner_id, project_id, episode_id, manifest_id)
    if item.status == "confirmed": raise project_service.ProjectConflictError("已确认的拍摄清单不可修改")
    if item.lock_version != lock_version: raise project_service.ProjectConflictError("拍摄清单版本冲突")
    if summary is not None: item.summary = summary
    if content is not None:
        episode = _episode(db, owner_id, project_id, episode_id)
        normalized = _normalize_manifest(content, episode)
        target_duration = _float((episode.script_settings or {}).get("target_duration") or episode.target_duration)
        normalized, issues = _analyze_manifest(normalized, target_duration)
        item.content = normalized
        item.total_duration = sum(s["duration"] for scene in normalized["scenes"] for s in scene["shots"])
        item.validation_errors = issues
    item.lock_version += 1
    db.commit(); db.refresh(item); return item


def _upsert_world(db: Session, owner_id: int, project_id: int, content: dict[str, Any]) -> tuple[dict[str, Character], dict[str, Location], dict[str, Prop]]:
    chars = {x.name: x for x in db.query(Character).filter_by(owner_id=owner_id, project_id=project_id).all()}
    locs = {x.name: x for x in db.query(Location).filter_by(owner_id=owner_id, project_id=project_id).all()}
    props = {x.name: x for x in db.query(Prop).filter_by(owner_id=owner_id, project_id=project_id).all()}
    for data in content.get("characters", []):
        name = str(data.get("name", "")).strip()
        if name and name not in chars:
            obj = Character(owner_id=owner_id, project_id=project_id, name=name); db.add(obj); db.flush(); chars[name] = obj
        if name:
            obj = chars[name]
            obj.identity = _text(data.get("core_identity") or data.get("identity"))
            obj.age_appearance = _text(data.get("age_appearance"))
            obj.appearance = _character_visual_prompt(data)
            negative = _text(data.get("negative_constraints"))
            obj.negative_traits = [negative] if negative else []
            variant = db.query(CharacterVariant).filter_by(character_id=obj.id, is_default=True).first()
            if not variant:
                variant = CharacterVariant(owner_id=owner_id, character_id=obj.id, name="基础造型", is_default=True); db.add(variant)
            variant.description = obj.appearance
            variant.wardrobe = _text(data.get("clothing")); variant.hairstyle = _text(data.get("hairstyle"))
    for data in content.get("locations", []):
        name = str(data.get("name", "")).strip()
        if name and name not in locs:
            obj = Location(owner_id=owner_id, project_id=project_id, name=name); db.add(obj); db.flush(); locs[name] = obj
        if name:
            obj = locs[name]
            obj.description = _text(data.get("description")); obj.spatial_layout = _text(data.get("spatial_layout"))
            obj.time_weather = _text(data.get("time_weather")); obj.lighting = _text(data.get("lighting"))
            obj.color_palette = _strings(data.get("color_palette")); obj.fixed_objects = _strings(data.get("fixed_objects"))
    for data in content.get("props", []):
        name = str(data.get("name", "")).strip()
        if name and name not in props:
            obj = Prop(owner_id=owner_id, project_id=project_id, name=name); db.add(obj); db.flush(); props[name] = obj
        if name:
            obj = props[name]
            obj.description = _text(data.get("description")); obj.appearance = _text(data.get("appearance"))
            obj.appearance_scope = _text(data.get("appearance_scope")); obj.continuity_note = _text(data.get("continuity_note"))
            owner_name = _text(data.get("owner_character_name")); obj.owner_character_id = chars[owner_name].id if owner_name in chars else None
    return chars, locs, props


def confirm_manifest(db: Session, owner_id: int, project_id: int, episode_id: int, manifest_id: int) -> ScriptManifestVersion:
    manifest = owned_manifest(db, owner_id, project_id, episode_id, manifest_id)
    if manifest.status == "confirmed": return manifest
    episode = _episode(db, owner_id, project_id, episode_id)
    content = _normalize_manifest(manifest.content or {}, episode); scenes = content.get("scenes", [])
    target_duration = _float((episode.script_settings or {}).get("target_duration") or episode.target_duration)
    content, issues = _analyze_manifest(content, target_duration)
    manifest.content = content; manifest.validation_errors = issues
    chars, locs, props = _upsert_world(db, owner_id, project_id, content)
    old_scene_ids = [x[0] for x in db.query(Scene.id).filter(Scene.episode_id == episode.id).all()]
    if old_scene_ids: db.query(Shot).filter(Shot.scene_id.in_(old_scene_ids)).delete(synchronize_session=False); db.query(Scene).filter(Scene.id.in_(old_scene_ids)).delete(synchronize_session=False)
    for si, data in enumerate(scenes):
        location_name = str(data.get("location_name") or data.get("heading") or "待确认场景")
        loc = locs.get(location_name)
        scene = Scene(owner_id=owner_id, episode_id=episode.id, scene_no=str(data.get("scene_no", si + 1)), heading=str(data.get("heading", location_name)),
            location_name=location_name, location_id=loc.id if loc else None, time_of_day=str(data.get("time_of_day", "")), interior_exterior=str(data.get("interior_exterior", "")),
            content=str(data.get("content", "")),
            elements=[{"type": kind, "text": _text(data.get(kind))} for kind in ("rhythm", "emotion", "atmosphere") if _text(data.get(kind))],
            character_ids=[chars[name].id for name in data.get("character_names", []) if name in chars],
            purpose=" / ".join(filter(None, [_text(data.get("rhythm")), _text(data.get("emotion"))])),
            target_duration=round(sum(_float(shot.get("duration")) for shot in data.get("shots", []))), sort_order=si, status="ready")
        db.add(scene); db.flush()
        for hi, data_shot in enumerate(data.get("shots", [])):
            char_ids = [chars[n].id for n in data_shot.get("character_names", []) if n in chars]
            prop_ids = [props[n].id for n in data_shot.get("prop_names", []) if n in props]
            shot = Shot(owner_id=owner_id, scene_id=scene.id, shot_no=hi + 1, sort_order=hi, status="ready", character_ids=char_ids, location_id=scene.location_id, prop_ids=prop_ids,
                purpose=_text(data_shot.get("purpose")), visual_description=_text(data_shot.get("visual_description")), action=_text(data_shot.get("action")),
                expression=_text(data_shot.get("expression")), dialogue=_text(data_shot.get("dialogue")), mood=_text(data_shot.get("mood")),
                shot_size=_text(data_shot.get("shot_size"), "中景"), camera_angle=_text(data_shot.get("camera_angle"), "平视"),
                camera_movement=_text(data_shot.get("camera_movement"), "固定"), composition=_text(data_shot.get("composition")),
                transition=_text(data_shot.get("transition")), duration=_float(data_shot.get("duration"), 3),
                production_settings={"manifest_prompt": data_shot.get("prompt", {}), "narration": _text(data_shot.get("narration")),
                    "inner_monologue": _text(data_shot.get("inner_monologue")), "scene_context": {
                        "sub_location": _text(data.get("sub_location")), "rhythm": _text(data.get("rhythm")),
                        "emotion": _text(data.get("emotion")), "atmosphere": _text(data.get("atmosphere")),
                    }})
            db.add(shot); db.flush()
            for cid in char_ids: db.add(ShotCharacterBinding(owner_id=owner_id, shot_id=shot.id, character_id=cid))
    db.query(ScriptManifestVersion).filter(ScriptManifestVersion.episode_id == episode.id, ScriptManifestVersion.id != manifest.id, ScriptManifestVersion.status == "confirmed").update({"status": "superseded"}, synchronize_session=False)
    manifest.status = "confirmed"; manifest.confirmed_at = _now(); episode.status = "manifest_confirmed"
    project = db.get(ShortDramaProject, project_id); project.stage = "assets"
    db.commit(); db.refresh(manifest); return manifest


def casting(db: Session, owner_id: int, project_id: int) -> dict[str, Any]:
    project_service.owned_project(db, owner_id, project_id)
    return {"characters": db.query(Character).options(selectinload(Character.variants)).filter_by(owner_id=owner_id, project_id=project_id).all(),
            "locations": db.query(Location).filter_by(owner_id=owner_id, project_id=project_id).all(), "props": db.query(Prop).filter_by(owner_id=owner_id, project_id=project_id).all(),
            "asset_versions": db.query(ProjectAssetVersion).filter_by(owner_id=owner_id, project_id=project_id).order_by(ProjectAssetVersion.entity_type, ProjectAssetVersion.entity_id, ProjectAssetVersion.version.desc()).all()}


def create_asset_version(db: Session, owner_id: int, project_id: int, entity_type: str, entity_id: int, *, resource_id: int | None, source_task_id: int | None, prompt: str, generation_snapshot: dict[str, Any]) -> ProjectAssetVersion:
    project_service.owned_project(db, owner_id, project_id)
    if entity_type not in {"character", "variant", "location", "prop"}: raise project_service.ProjectConflictError("不支持的素材实体类型")
    if source_task_id:
        existing = db.query(ProjectAssetVersion).filter_by(owner_id=owner_id, project_id=project_id,
            entity_type=entity_type, entity_id=entity_id, source_task_id=source_task_id).first()
        if existing:
            return existing
    version = int(db.query(func.max(ProjectAssetVersion.version)).filter_by(project_id=project_id, entity_type=entity_type, entity_id=entity_id).scalar() or 0) + 1
    item = ProjectAssetVersion(owner_id=owner_id, project_id=project_id, entity_type=entity_type, entity_id=entity_id, version=version,
        resource_id=resource_id, source_task_id=source_task_id, prompt=prompt, generation_snapshot=generation_snapshot, status="candidate")
    db.add(item); db.commit(); db.refresh(item); return item


def auto_link_turnaround(db: Session, owner_id: int, project_id: int, entity_type: str, entity_id: int,
                         resource_id: int, source_task_id: int | None, prompt: str,
                         generation_snapshot: dict[str, Any]) -> ProjectAssetVersion:
    """Persist and associate a completed three-view without replacing the main image."""
    item = create_asset_version(db, owner_id, project_id, entity_type, entity_id,
        resource_id=resource_id, source_task_id=source_task_id, prompt=prompt, generation_snapshot=generation_snapshot)
    model = Character if entity_type == "character" else CharacterVariant if entity_type == "variant" else None
    target = db.get(model, entity_id) if model else None
    if target and target.owner_id == owner_id:
        target.reference_resource_ids = list(dict.fromkeys([*(target.reference_resource_ids or []), resource_id]))
        item.status = "confirmed"
        db.commit(); db.refresh(item)
    return item


def adopt_asset_version(db: Session, owner_id: int, project_id: int, version_id: int) -> ProjectAssetVersion:
    item = db.query(ProjectAssetVersion).filter_by(id=version_id, owner_id=owner_id, project_id=project_id).first()
    if not item: raise project_service.ProjectNotFoundError("素材版本不存在")
    db.query(ProjectAssetVersion).filter_by(project_id=project_id, entity_type=item.entity_type, entity_id=item.entity_id).update({"is_current": False}, synchronize_session=False)
    item.is_current = True; item.status = "confirmed"
    if item.resource_id:
        model = {"character": Character, "variant": CharacterVariant, "location": Location}.get(item.entity_type)
        if model: setattr(db.get(model, item.entity_id), "primary_resource_id", item.resource_id)
        elif item.entity_type == "prop": db.get(Prop, item.entity_id).resource_id = item.resource_id
    db.commit(); db.refresh(item); return item


def bind_character(db: Session, owner_id: int, project_id: int, shot_id: int, character_id: int, variant_id: int | None) -> ShotCharacterBinding:
    shot = db.query(Shot).join(Scene).join(Episode).filter(Shot.id == shot_id, Episode.project_id == project_id, Episode.owner_id == owner_id).first()
    if not shot: raise project_service.ProjectNotFoundError("镜头不存在")
    item = db.query(ShotCharacterBinding).filter_by(shot_id=shot_id, character_id=character_id).first()
    if not item: item = ShotCharacterBinding(owner_id=owner_id, shot_id=shot_id, character_id=character_id); db.add(item)
    item.variant_id = variant_id; item.inheritance_source = "shot_override" if variant_id else "character_default"
    db.commit(); db.refresh(item); return item
