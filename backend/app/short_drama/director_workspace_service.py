"""Episode director workspace using the shared ComfyUI queue and immutable Takes."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import re
from typing import Any
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models import (Batch, Character, CharacterVariant, Episode, GenerationType,
    GenerationTypeConfigVersion, Location, ProjectAssetVersion, Prop, Resource, Scene, Shot, ShotTaskLink,
    Take, Task, Workflow, WorkflowVersion)
from app.models.short_drama import ShotCharacterBinding, ScriptManifestVersion
from app.short_drama.dialogue import total_duration
from app.schemas.director_workspace import WorkspaceDraft, DirectorGenerate
from app.services import generation_type_config_service as config_service
from app.services.generation_type_service import get_select_options, get_select_default
from app.short_drama import production_service as production, project_service
from app.comfy.prompt_builder import build_prompt
from app.queue.dispatcher import resolve_multimedia_target

class Conflict(ValueError): pass

ROLES = {"prompt", "negative_prompt", "first_frame", "last_frame", "character_references",
         "scene_references", "prop_references", "reference_images", "duration", "aspect_ratio"}
IMAGE_ROLES = {"first_frame", "last_frame", "character_references", "scene_references", "prop_references", "reference_images"}
DEFAULT_NEGATIVE_RULES = (
    "严禁多手多脚肢体穿模",
    "严禁画面内出现字幕文字",
    "不得改变服装",
    "不得改变发型颜色",
)


def with_default_negative(value: object = "") -> str:
    """Keep user exclusions and append the production-wide identity rules once."""
    result = str(value or "").strip(" ，,。；;\n")
    for rule in DEFAULT_NEGATIVE_RULES:
        if rule not in result:
            result = f"{result}，{rule}" if result else rule
    return result


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def context(db: Session, owner: int, project_id: int, shot_id: int) -> tuple:
    return production._shot_context(db, owner, project_id, shot_id)


def turnaround_map(db: Session, owner: int, project_id: int) -> dict[tuple[str, int], int]:
    """Latest three-view (turnaround) image per character / variant, from asset versions."""
    versions = db.query(ProjectAssetVersion).filter(
        ProjectAssetVersion.project_id==project_id, ProjectAssetVersion.owner_id==owner,
        ProjectAssetVersion.entity_type.in_(["character","variant"])
        ).order_by(ProjectAssetVersion.id.desc()).all()
    result: dict[tuple[str, int], int] = {}
    for item in versions:
        purpose = (item.generation_snapshot or {}).get("purpose")
        if purpose not in {"character_turnaround", "asset_turnaround"} or not item.resource_id:
            continue
        key = (item.entity_type, item.entity_id)
        result.setdefault(key, item.resource_id)
    return result


def character_mode_map(shot: Shot) -> dict[int, str]:
    choices = ((shot.production_settings or {}).get("director_workspace") or {}).get("asset_choices") or {}
    return {int(c["character_id"]): c.get("image_mode") or "primary"
            for c in choices.get("characters") or []}


def checked_orders(shot: Shot) -> dict[str, int]:
    """One check-order space across frames / extras / characters / location / props.
    Keys: frame:<id>, extra:<rid>, char:<cid>, location, prop:<pid>; value is 1-based rank."""
    choices = ((shot.production_settings or {}).get("director_workspace") or {}).get("asset_choices") or {}
    entries: list[tuple[str, int, int]] = []  # (key, order, tiebreak)
    for frame in (((shot.production_settings or {}).get("director_workspace") or {}).get("frames") or []):
        if frame.get("enabled", True):
            entries.append((f"frame:{frame['id']}", int(frame.get("order") or 0), 0))
    for index, extra in enumerate(choices.get("extras") or []):
        if extra.get("enabled", True):
            entries.append((f"extra:{extra.get('resource_id')}", int(extra.get("order") or 0), index))
    for index, choice in enumerate(choices.get("characters") or []):
        if choice.get("enabled", True):
            entries.append((f"char:{choice.get('character_id')}", int(choice.get("order") or 0), index))
    if choices.get("location_enabled"):
        entries.append(("location", int(choices.get("location_order") or 0), 0))
    for pid, order in (choices.get("prop_orders") or {}).items():
        if order: entries.append((f"prop:{pid}", int(order or 0), 0))
    entries.sort(key=lambda e: (e[1], e[2]))
    return {key: rank for rank, (key, *_ ) in enumerate(entries, start=1)}


def extras(db: Session, owner: int, shot: Shot) -> list[dict]:
    """Library resources attached to the shot; only checked ones feed workflow inputs."""
    orders = checked_orders(shot)
    result = []
    for item in (((shot.production_settings or {}).get("director_workspace") or {}).get("asset_choices") or {}).get("extras") or []:
        rid, media = item.get("resource_id"), item.get("media_type")
        if not isinstance(rid, int) or media not in {"image", "audio", "video"}:
            continue
        resource = db.query(Resource).filter_by(id=rid, owner_id=owner, media_type=media, deleted_at=None).first()
        if not resource:
            continue
        result.append({"resource_id": rid, "media_type": media, "label": str(item.get("label") or "")[:200],
                       "enabled": bool(item.get("enabled", True)), "order": int(item.get("order") or 0),
                       "check_order": orders.get(f"extra:{rid}", 0),
                       "filename": resource.filename})
    result.sort(key=lambda e: (not e["enabled"], e["order"], e["resource_id"]))
    return result


def latest_asset_version(db: Session, owner: int, project_id: int, entity_type: str, entity_id: int):
    return (db.query(ProjectAssetVersion)
        .filter_by(owner_id=owner, project_id=project_id, entity_type=entity_type, entity_id=entity_id)
        .order_by(ProjectAssetVersion.is_current.desc(), ProjectAssetVersion.id.desc())
        .first())


def latest_asset_prompt(db: Session, owner: int, project_id: int, entity_type: str, entity_id: int) -> str:
    """Return the latest saved generation prompt for a bound production asset."""
    version = latest_asset_version(db, owner, project_id, entity_type, entity_id)
    return str(version.prompt or "").strip() if version else ""


def resources(db: Session, owner: int, project_id: int, shot: Shot) -> list[dict]:
    result = []
    orders = checked_orders(shot)
    bindings = {b.character_id: b for b in db.query(ShotCharacterBinding).filter_by(shot_id=shot.id, owner_id=owner)}
    modes = character_mode_map(shot)
    turns = turnaround_map(db, owner, project_id)
    char_choices = {int(c["character_id"]): c for c in (((shot.production_settings or {}).get("director_workspace") or {}).get("asset_choices") or {}).get("characters") or []}
    for cid in shot.character_ids or []:
        item = db.query(Character).filter_by(id=cid, project_id=project_id, owner_id=owner).first()
        if not item: continue
        binding = bindings.get(cid)
        variant = db.query(CharacterVariant).filter_by(id=binding.variant_id, character_id=cid, owner_id=owner).first() if binding and binding.variant_id else None
        if not variant:
            variant = db.query(CharacterVariant).filter_by(character_id=cid, owner_id=owner, is_default=True).first()
        source = variant or item
        choice = char_choices.get(cid) or {}
        enabled = bool(choice.get("enabled", True))
        image_mode = choice.get("image_mode") or "primary"
        # A costume variant may only describe the look and have no image of its
        # own. Always fall back to the adopted character image so the director
        # workspace can still display and submit a valid identity reference.
        rid = (variant.primary_resource_id if variant else None) or item.primary_resource_id
        if image_mode == "turnaround":
            variant_turn = turns.get(("variant", variant.id)) if variant else None
            rid = variant_turn or turns.get(("character", item.id)) or rid
        entity_type = "variant" if variant else "character"
        asset_version = latest_asset_version(db, owner, project_id, entity_type, source.id)
        if not asset_version and variant:
            asset_version = latest_asset_version(db, owner, project_id, "character", item.id)
        asset_prompt = str(asset_version.prompt or "").strip() if asset_version else ""
        result.append({"role":"character_references", "name":item.name + (" · " + variant.name if variant else " · 基础造型"),
                       "stable_key": f"CHR-{cid:03d}", "entity_id":cid, "variant_id":variant.id if variant else None, "resource_id":rid,
                       "asset_version_id": asset_version.id if asset_version else None, "asset_version": asset_version.version if asset_version else None,
                       "image_mode":image_mode, "enabled":enabled, "check_order":orders.get(f"char:{cid}", 0),
                       "updated_at":str(source.updated_at),
                       "description":((variant.description or variant.wardrobe) if variant else (item.appearance or item.identity)) or asset_prompt})
    location = db.query(Location).filter_by(id=shot.location_id, project_id=project_id, owner_id=owner).first() if shot.location_id else None
    if location:
        location_version = latest_asset_version(db, owner, project_id, "location", location.id)
        result.append({"role":"scene_references", "name":location.name, "stable_key": f"SCN-{location.id:03d}", "entity_id":location.id,
                       "resource_id":location.primary_resource_id, "asset_version_id": location_version.id if location_version else None,
                       "asset_version": location_version.version if location_version else None, "enabled":bool((((shot.production_settings or {}).get("director_workspace") or {}).get("asset_choices") or {}).get("location_enabled", False)),
                       "check_order":orders.get("location", 0), "updated_at":str(location.updated_at),
                       "description":"；".join(filter(None, [location.description, location.spatial_layout])) or latest_asset_prompt(db, owner, project_id, "location", location.id)})
    for pid in shot.prop_ids or []:
        prop = db.query(Prop).filter_by(id=pid, project_id=project_id, owner_id=owner).first()
        if prop:
            prop_version = latest_asset_version(db, owner, project_id, "prop", prop.id)
            result.append({"role":"prop_references", "name":prop.name, "stable_key": f"PRP-{prop.id:03d}", "entity_id":prop.id,
                           "resource_id":prop.resource_id, "asset_version_id": prop_version.id if prop_version else None,
                           "asset_version": prop_version.version if prop_version else None, "enabled":bool((((shot.production_settings or {}).get("director_workspace") or {}).get("asset_choices") or {}).get("prop_orders", {}).get(str(pid))),
                           "check_order":orders.get(f"prop:{pid}", 0), "updated_at":str(prop.updated_at),
                           "description":"；".join(filter(None, [prop.description, prop.appearance])) or latest_asset_prompt(db, owner, project_id, "prop", prop.id)})
    return result


CAMERA_KEYWORDS = (("环绕", "Orbital / Arc shot"), ("弧线", "Arc shot"), ("跟", "Tracking shot"), ("移", "Tracking shot"),
                   ("摇", "Pan"), ("推", "Push in / Dolly in"), ("拉", "Pull out / Dolly out"), ("升降", "Tilt"),
                   ("甩", "Whip pan"), ("固定", "Static / Fixed"))


def camera_keyword(movement: str) -> str:
    """Map Chinese camera movement terms to the H3 English keyword vocabulary."""
    text = (movement or "").strip()
    for key, value in CAMERA_KEYWORDS:
        if key in text: return value
    return text or "Static / Fixed"


def _prompt_segment(shot: Shot, key: str) -> str:
    """Read a manifest_prompt segment (AI 分析结果) from production settings."""
    prompt = (shot.production_settings or {}).get("manifest_prompt") or {}
    effective = prompt.get("effective") if isinstance(prompt.get("effective"), dict) else {}
    original = prompt.get("original") if isinstance(prompt.get("original"), dict) else {}
    return str(effective.get(key) or original.get(key) or "").strip()


def shot_dialogue(shot: Shot) -> str:
    """Older manifests persist speech in dialogue_lines instead of Shot.dialogue."""
    explicit = (shot.dialogue or "").strip()
    if explicit:
        return explicit
    lines = (shot.production_settings or {}).get("dialogue_lines") or []
    result = []
    for line in lines if isinstance(lines, list) else []:
        if not isinstance(line, dict):
            continue
        text = str(line.get("text") or "").strip()
        speaker = str(line.get("speaker") or "").strip()
        if not text:
            continue
        result.append(f"{speaker}：{text}" if speaker else text)
    return "\n".join(result)


def confirmed_manifest_dialogue(db: Session, shot: Shot) -> str:
    """Recover dialogue for rows created by the old pre-analysis confirmation bug."""
    local = shot_dialogue(shot)
    if local:
        return local
    scene = db.get(Scene, shot.scene_id)
    if not scene:
        return ""
    manifest = (db.query(ScriptManifestVersion)
        .filter_by(episode_id=scene.episode_id, status="confirmed")
        .order_by(ScriptManifestVersion.id.desc()).first())
    scenes = ((manifest.content or {}).get("scenes") or []) if manifest else []
    if not (0 <= scene.sort_order < len(scenes)):
        return ""
    shots = scenes[scene.sort_order].get("shots") or []
    if not (0 <= shot.sort_order < len(shots)):
        return ""
    result = []
    for line in shots[shot.sort_order].get("dialogue_lines") or []:
        if not isinstance(line, dict) or not str(line.get("text") or "").strip():
            continue
        speaker, text = str(line.get("speaker") or "").strip(), str(line["text"]).strip()
        result.append(f"{speaker}：{text}" if speaker else text)
    return "\n".join(result)


def video_prompt_inputs(shot: Shot) -> dict:
    atmosphere=((shot.production_settings or {}).get("scene_context") or {}).get("atmosphere") or ""
    result={key:getattr(shot,key) or "" for key in ("visual_description","action","expression","timeline_storyboard","continuity","shot_size","camera_angle","camera_movement","composition","transition")}
    result.update(visual_description=_prompt_segment(shot,"base_visual") or shot.visual_description or "",
                  visual_style=_prompt_segment(shot,"visual_style") or atmosphere or shot.mood or "",
                  composition=_prompt_segment(shot,"composition_guide") or shot.composition or "",
                  dialogue=shot_dialogue(shot),atmosphere=atmosphere,
                  negative_constraints=_prompt_segment(shot,"negative_constraints") or "no other people, no facial distortion, no extra limbs, no text, no watermark, no camera static, no out of focus")
    workspace=(shot.production_settings or {}).get("director_workspace") or {}
    overrides=workspace.get("prompt_inputs") or {}
    touched=set(workspace.get("prompt_input_overrides") or [])
    result.update({k:v for k,v in overrides.items() if k in result and v is not None
                   and not (k=="dialogue" and v=="" and k not in touched)})
    return result


def video_prompt(shot: Shot, assets: list[dict], ratio: str = "9:16", inputs: dict | None = None, picture_refs: list[dict] | None = None) -> str:
    """MiniMax H3 Ref2VA 六段式结构化视频提示词。

    依据《MiniMax H3 Ref2VA 全参考模式提示词编写规范》：六个节段固定顺序、字段名小写、
    叙述中文（对白 <d>[中文]</d> 保留原语言）、角色图在 Subject 内引用（不建独立 Picture）、
    场景也定义为 Subject、画面构成放 detailed_description、Negative 精简。
    数据来源：AI 分析（manifest_prompt.effective / shot 字段 / scene_context）+ 勾选资产。
    """
    inputs = inputs or video_prompt_inputs(shot)
    assets=deepcopy(assets)
    picture_refs=deepcopy(picture_refs or [])
    picture_numbers={item["resource_id"]:index for index,item in enumerate(picture_refs,start=1)}
    descriptions=((shot.production_settings or {}).get("director_workspace") or {}).get("prompt_asset_descriptions") or {}
    for asset in assets:
        key=f"{asset['role']}:{asset['entity_id']}"
        if key in descriptions: asset["description"]=descriptions[key]
    settings = shot.production_settings or {}
    scene_context = {"atmosphere":inputs["atmosphere"]}
    style = inputs["visual_style"]
    base_visual = inputs["visual_description"]
    # Every bound asset belongs to the textual prompt. `enabled` only controls
    # whether its media file is sent as a ComfyUI reference input.
    characters = [a for a in assets if a["role"] == "character_references" and a.get("enabled", True)]
    scene_asset = next((a for a in assets if a["role"] == "scene_references" and a.get("enabled", True)), None)
    props = [a for a in assets if a["role"] == "prop_references" and a.get("enabled", True)]
    dialogue = inputs["dialogue"]

    # ---- 1. subject_definitions：人物/场景/道具全部定义成 Subject（角色图在其内引用） ----
    lines = ["subject_definitions:"]
    subject_no = 0
    subject_keys: list[tuple[int, dict]] = []
    for asset in characters:
        subject_no += 1
        name = asset["name"].split(" · ")[0]
        appearance = asset.get("description") or "外观以参考图为准"
        picture_no=picture_numbers.get(asset.get("resource_id"))
        ref = f" 完全参照 <Picture {picture_no}> 外观，<Picture {picture_no}> 不得展示参考图背景。" if picture_no else ""
        lines.append(f"- <Subject {subject_no}>: {name}，{appearance}。{ref}".strip())
        subject_keys.append((subject_no, asset))
    scene_subject = None
    if scene_asset:
        subject_no += 1
        scene_subject = subject_no
        detail = scene_asset.get("description") or scene_asset["name"]
        picture_no=picture_numbers.get(scene_asset.get("resource_id"))
        ref = f" 完全参照 <Picture {picture_no}> 场景外观。" if picture_no else " 无参考图，由文字描述定义。"
        lines.append(f"- <Subject {subject_no}>: {scene_asset['name']}场景，{detail}。{ref}".strip())
    for asset in props:
        subject_no += 1
        picture_no=picture_numbers.get(asset.get("resource_id"))
        ref = f" 完全参照 <Picture {picture_no}> 外观。" if picture_no else " 无参考图，由文字描述定义。"
        lines.append(f"- <Subject {subject_no}>: {asset['name']}，{asset.get('description') or '道具'}。{ref}".strip())
    if not lines[1:]:
        lines.append(f"- <Subject 1>: {scene_asset['name'] if scene_asset else '主场景'}，无参考图，由文字描述定义。")
    for number, item in enumerate(picture_refs, start=1):
        if item.get("source") != "context":
            lines.append(f"- <Picture {number}>: {item['label']}。{item['description']}。用途：{item['purpose']}。")

    # ---- 2. summary：任务类型、目标视频、时长、画幅、镜头运动概括 ----
    duration = total_duration(shot.duration,shot.production_settings or {})
    movement = camera_keyword(inputs['camera_movement'])
    if inputs['camera_movement'] and inputs['camera_movement'] != movement: movement += f"（{inputs['camera_movement']}）"
    summary = (f"{duration} 秒单镜头，{ratio} 画幅{'，' + style if style else ''}。"
               f"镜头运动：{movement}（{inputs['shot_size'] or '中景'}·{inputs['camera_angle'] or '平视'}）。"
               f"主体动作：{(inputs['action'] or base_visual)[:40]}。")
    lines.append("summary:")
    lines.append(f"- {summary}")

    # ---- 3. retention_analysis：一致性说明书（只管参考元素一致性） ----
    lines.append("retention_analysis:")
    for number, asset in subject_keys:
        variant_note = "" if " · " not in asset["name"] else f"（{asset['name'].split(' · ', 1)[1]}造型）"
        lines.append(f"- <Subject {number}>: fully_preserved {asset['name'].split(' · ')[0]}全套外观{variant_note}，动作见 detailed_description。")
    if scene_subject:
        lines.append(f"- <Subject {scene_subject}>: fully_preserved {scene_asset['name']}场景要素（与参考图或文字定义一致）。")

    # ---- 4. detailed_description：short-drama-director 视频提示词正文 ----
    lines.append("detailed_description:")
    # detailed_description 只承载可执行的时间轴与接续状态；
    # 画幅、资产和负面约束已经分别由 summary、subject_definitions、
    # retention_analysis 与外层 Negative 表达，避免重复污染模型输入。
    skill_characters = [asset for asset in assets if asset["role"] == "character_references" and asset.get("enabled", True)]
    skill_scene = next((asset for asset in assets if asset["role"] == "scene_references" and asset.get("enabled", True)), None)

    raw_negative = str(inputs.get("negative_constraints") or "").strip(" ，,。")
    negative = raw_negative.replace("避免", "严禁").replace("保持脸部清晰", "严禁脸部模糊")
    negative = with_default_negative(negative)

    lines.append("【时间轴分镜】：")
    timeline = str(inputs.get("timeline_storyboard") or "").strip()
    def clean_dialogue(part: str) -> str:
        value = part.strip()
        match = re.match(r'^(.*?[：:])\s*[“"](.*?)[”"]$', value)
        return f"{match.group(1)}{match.group(2)}" if match else value.strip('“”"')
    dialogue_parts = [clean_dialogue(part) for part in dialogue.splitlines() if part.strip()]
    timeline_lines: list[str] = []
    if re.search(r"\b\d{1,2}:\d{2}(?:\.\d+)?\s*[-–—]\s*\d{1,2}:\d{2}(?:\.\d+)?\b", timeline):
        timeline_lines.extend(timeline.splitlines())
        if dialogue_parts and not all(part in timeline for part in dialogue_parts):
            timeline_lines.append(f"台词：【{'；'.join(dialogue_parts)}】")
    else:
        beats = [
            match.strip()
            for match in re.split(r"(?:^|[；;。]\s*)\d+[.、]\s*", timeline)
            if match.strip()
        ]
        if not beats:
            beats = [str(inputs.get("action") or base_visual or "主体按剧本动作展开").strip()]
        # A Shot is one generation group. Keep its action chain intact while
        # grouping dense beats into usable 4–6 second internal camera units.
        segment_count = max(1, min(len(beats), math.ceil(duration / 6)))
        grouped_beats = []
        for group_index in range(segment_count):
            group_start = math.floor(group_index * len(beats) / segment_count)
            group_end = math.floor((group_index + 1) * len(beats) / segment_count)
            grouped_beats.append("，随后".join(beats[group_start:group_end]))
        segment = duration / len(grouped_beats)
        for index, beat in enumerate(grouped_beats, 1):
            begin = (index - 1) * segment
            finish = duration if index == len(grouped_beats) else index * segment
            def stamp(value: float) -> str:
                minutes = int(value // 60)
                seconds = value - minutes * 60
                return f"{minutes:02d}:{seconds:04.1f}" if abs(seconds - round(seconds)) > .01 else f"{minutes:02d}:{int(round(seconds)):02d}"
            shot_size = inputs["shot_size"] or "中景"
            angle = inputs["camera_angle"] or "平视"
            target = ""
            for asset in skill_characters:
                name = asset["name"].split(" · ")[0]
                if name in beat:
                    target = f"·对准@{name}"
                    break
            detail = f"{stamp(begin)}-{stamp(finish)} [镜头{index}] {shot_size}·{angle}·{movement}{target}。{beat}"
            if index == 1 and base_visual and base_visual not in beat:
                detail += f"。画面：{base_visual}"
            if index == 1 and inputs["expression"]:
                detail += f"。表演：{inputs['expression']}"
            if index == 1 and scene_context.get("atmosphere"):
                detail += f"。声音：{scene_context['atmosphere']}"
            if index == 1 and dialogue_parts:
                detail += f"。台词：【{'；'.join(dialogue_parts)}】"
            timeline_lines.append(detail)

    start_ref = next(((index, item) for index, item in enumerate(picture_refs, 1) if item.get("frame_kind") == "start"), None)
    end_ref = next(((index, item) for index, item in enumerate(picture_refs, 1) if item.get("frame_kind") == "end"), None)
    nonempty = [index for index, value in enumerate(timeline_lines) if value.strip()]
    if start_ref and nonempty:
        number, item = start_ref
        cue = f"画面开始于首帧[{str(item.get('description') or '以首帧画面为准').strip(' 。')}]<Picture {number}>，"
        marker_end = timeline_lines[nonempty[0]].find("]")
        insert_at = marker_end + 1 if marker_end >= 0 else 0
        timeline_lines[nonempty[0]] = timeline_lines[nonempty[0]][:insert_at] + " " + cue + timeline_lines[nonempty[0]][insert_at:].lstrip()
    if end_ref and nonempty:
        number, item = end_ref
        cue = f"画面结束于尾帧[{str(item.get('description') or '以尾帧画面为准').strip(' 。')}]<Picture {number}>，"
        timeline_lines[nonempty[-1]] = timeline_lines[nonempty[-1]].rstrip(" 。") + "。" + cue
    lines.extend(timeline_lines)

    continuity = str(inputs.get("continuity") or "").strip()
    if not continuity:
        continuity = "；".join(filter(None, [
            inputs.get("composition") or "",
            f"转场：{inputs['transition']}" if inputs.get("transition") else "",
        ]))
    lines.append(f"【接续状态】：{continuity or '保持人物位置、视线、动作与道具状态连续，下一组从本组结尾状态接入'}")

    # ---- 5. overall_soundscape：环境音 + 物理声音 ----
    soundscape = []
    if scene_context.get("atmosphere"): soundscape.append(f"{scene_context['atmosphere']}的环境氛围声")
    if scene_asset: soundscape.append(f"{scene_asset['name']}环境音")
    if dialogue: soundscape.append("对白声（见 detailed_description 的台词标注）")
    if inputs['action']: soundscape.append("动作对应的物理音效（脚步、衣物摩擦、道具触碰）")
    lines.append("overall_soundscape:")
    lines.append(f"- {'，'.join(soundscape) if soundscape else '与画面匹配的自然环境音'}。")

    # ---- 6. non_diegetic_music：无配乐时写 N/A ----
    lines.append("non_diegetic_music: N/A")

    # ---- Negative：保留镜头约束，并强制补齐项目级人物一致性与画面安全规则 ----
    lines.append(f"Negative: {negative},")
    return "\n".join(lines)


def default_draft(shot: Shot) -> dict:
    plan = (shot.production_settings or {}).get("keyframe_plan") or {}
    frames = [{"id":"start", "kind":"start", "time":0, "prompt":plan.get("first_frame_prompt") or shot.visual_description},
              {"id":"end", "kind":"end", "time":shot.duration, "prompt":plan.get("last_frame_prompt") or ""}]
    for index, item in enumerate((plan.get("keyframes") or [])[:28]):
        if isinstance(item, dict):
            try: time = float(item.get("time") or 0)
            except (TypeError, ValueError): time = 0
            if not math.isfinite(time): time = 0
            frames.insert(-1, {"id":f"key_{index+1}", "kind":"key", "time":min(shot.duration, max(0, time)),
                               "prompt":str(item.get("prompt") or item.get("description") or "")})
    saved = (shot.production_settings or {}).get("director_workspace")
    return WorkspaceDraft.model_validate(saved or {"frames":frames, "video_prompt":shot.video_prompt or "；".join(filter(None,[shot.visual_description,shot.action,shot.expression,shot.camera_movement]))}).model_dump()


def draft_with_defaults(db: Session, owner: int, project_id: int, shot: Shot) -> dict:
    """Fresh draft with AI-composited video prompt and brief ratio when nothing saved yet."""
    saved = (shot.production_settings or {}).get("director_workspace")
    draft = default_draft(shot)
    inputs = video_prompt_inputs(shot)
    # Preserve explicit workspace edits, including intentional clearing.
    workspace = (shot.production_settings or {}).get("director_workspace") or {}
    overrides = workspace.get("prompt_inputs") or {}
    touched = set(workspace.get("prompt_input_overrides") or [])
    if "dialogue" not in overrides or (overrides.get("dialogue")=="" and "dialogue" not in touched):
        inputs["dialogue"] = confirmed_manifest_dialogue(db, shot)
    draft["prompt_inputs"] = inputs
    if saved: return draft
    project = project_service.owned_project(db, owner, project_id)
    ratio = project.brief.aspect_ratio if project.brief else "9:16"
    draft["video_prompt"] = shot.video_prompt or video_prompt(shot, resources(db, owner, project_id, shot), ratio, inputs)
    return draft


def compose_video_prompt_view(db: Session, owner: int, project_id: int, shot_id: int) -> str:
    """Recompose the three-layer video prompt from current AI analysis and assets."""
    shot, *_ = context(db, owner, project_id, shot_id)
    project = project_service.owned_project(db, owner, project_id)
    ratio = project.brief.aspect_ratio if project.brief else "9:16"
    inputs = draft_with_defaults(db, owner, project_id, shot)["prompt_inputs"]
    return video_prompt(shot, resources(db, owner, project_id, shot), ratio, inputs, checked_image_references(db, owner, project_id, shot))

def save_draft(db: Session, owner: int, project_id: int, shot_id: int, revision: int, draft: WorkspaceDraft) -> None:
    shot, *_ = context(db, owner, project_id, shot_id)
    ids = [frame.id for frame in draft.frames]
    if len(ids) != len(set(ids)) or "start" not in ids or "end" not in ids:
        raise ValueError("首帧和尾帧必须保留，关键帧编号不可重复")
    for frame in draft.frames:
        if (frame.id in ("start","end") and frame.kind != frame.id) or (frame.id.startswith("key_") and frame.kind != "key"):
            raise ValueError("关键帧编号与用途不一致")
        if frame.time > shot.duration: raise ValueError("关键帧时间超出镜头时长")
    # Extras must point at real, owned library resources; characters must be project members.
    project = project_service.owned_project(db, owner, project_id)
    for extra in draft.asset_choices.extras:
        if not db.query(Resource).filter_by(id=extra.resource_id, owner_id=owner, media_type=extra.media_type, deleted_at=None).first():
            raise ValueError(f"视频资源 #{extra.resource_id} 不存在、类型不符或已删除")
    for choice in draft.asset_choices.characters:
        if not db.query(Character).filter_by(id=choice.character_id, project_id=project_id, owner_id=owner).first():
            raise ValueError(f"角色 #{choice.character_id} 不属于当前项目")
    settings = deepcopy(shot.production_settings or {})
    settings["director_workspace"] = draft.model_dump()
    result = db.execute(update(Shot).where(Shot.id==shot.id, Shot.lock_version==revision).values(production_settings=settings, lock_version=revision+1))
    if result.rowcount != 1:
        db.rollback(); raise Conflict("镜头已被其他页面更新，请重新载入后再保存")
    db.commit()


def workflow_list(db: Session, owner: int, project_id: int) -> list[dict]:
    project = project_service.owned_project(db, owner, project_id)
    bindings = (project.settings or {}).get("director_workflow_bindings", {})
    result = []
    for gt in db.query(GenerationType).filter(GenerationType.enabled.is_(True), GenerationType.deleted_at.is_(None), GenerationType.media_type.in_(["image","video"])):
        published = db.get(GenerationTypeConfigVersion, gt.published_config_version_id) if gt.published_config_version_id else None
        config = published.config if published else config_service.build_default_config(db, gt)
        for item in config_service.build_runtime_workflows(db, gt, config):
            workflow = db.get(Workflow, item["workflow_id"])
            if workflow.owner_id not in (None, owner): continue
            mapping = {p["key"]:p["semantic_role"] for p in item["parameters"] if p.get("semantic_role") in ROLES}
            if str(item["workflow_version_id"]) in bindings:
                mapping = bindings[str(item["workflow_version_id"])]
            roles = set(mapping.values())
            modes = ["manual"]
            if "first_frame" in roles: modes.append("first")
            if {"first_frame","last_frame"} <= roles: modes.append("first_last")
            if roles & {"reference_images","character_references","scene_references","prop_references"}: modes.append("references")
            result.append({**item,"generation_type_id":gt.id,"generation_type_name":gt.name,"media_type":gt.media_type,
                           "config_version_id":published.id if published else None,"mapping":mapping,"modes":modes})
    return result


def get_workflow(db: Session, owner: int, project_id: int, version_id: int) -> dict:
    item = next((w for w in workflow_list(db, owner, project_id) if w["workflow_version_id"]==version_id), None)
    if not item: raise ValueError("工作流不可用、未发布绑定或无访问权限，请重新选择")
    return item


def bind_workflow(db: Session, owner: int, project_id: int, version_id: int, mapping: dict) -> None:
    workflow = get_workflow(db, owner, project_id, version_id)
    schema = {p["key"]:p for p in workflow["parameters"]}
    used = set()
    for key, role in mapping.items():
        if not role: continue
        if key not in schema or role not in ROLES: raise ValueError("输入用途映射包含未知字段或用途")
        if role in used: raise ValueError("同一用途不能绑定多个字段；多图请使用多选参考参数")
        used.add(role)
        kind = schema[key].get("type")
        if role in IMAGE_ROLES and kind != "image": raise ValueError("图片用途必须绑定图片参数")
        if role in {"first_frame","last_frame"} and schema[key].get("multiple"): raise ValueError("首尾帧必须使用单图参数")
        if role=="duration" and kind not in {"int","float","slider","select"}: raise ValueError("时长用途必须绑定数值或下拉参数")
        if role in {"prompt","negative_prompt"} and kind not in {"text","textarea"}: raise ValueError("提示词用途必须绑定文本参数")
    project = project_service.owned_project(db, owner, project_id)
    settings = deepcopy(project.settings or {})
    bindings = settings.setdefault("director_workflow_bindings", {})
    bindings[str(version_id)] = {k:v for k,v in mapping.items() if v}
    project.settings = settings; db.commit()


def update_refs(db: Session, owner: int, project_id: int, shot_id: int, character_ids: list[int],
                bindings: dict[str, int | None], location_id: int | None, prop_ids: list[int]) -> None:
    """Bind characters / location / props onto the shot; characters may pick a costume variant."""
    shot, *_ = context(db, owner, project_id, shot_id)
    project = project_service.owned_project(db, owner, project_id)
    cleaned = list(dict.fromkeys(int(c) for c in character_ids))
    for cid in cleaned:
        if not db.query(Character).filter_by(id=cid, project_id=project_id, owner_id=owner).first():
            raise ValueError(f"角色 #{cid} 不属于当前项目")
    variants: dict[int, int | None] = {}
    for key, variant_id in (bindings or {}).items():
        try: cid = int(key)
        except (TypeError, ValueError): raise ValueError("角色绑定编号无效")
        if cid not in cleaned: continue
        if variant_id is not None:
            if not db.query(CharacterVariant).filter_by(id=int(variant_id), character_id=cid, owner_id=owner).first():
                raise ValueError(f"角色 #{cid} 的服装变体 #{variant_id} 不存在")
            variants[cid] = int(variant_id)
        else:
            variants[cid] = None
    if location_id is not None and not db.query(Location).filter_by(id=location_id, project_id=project_id, owner_id=owner).first():
        raise ValueError(f"场景 #{location_id} 不属于当前项目")
    props = list(dict.fromkeys(int(p) for p in prop_ids))
    for pid in props:
        if not db.query(Prop).filter_by(id=pid, project_id=project_id, owner_id=owner).first():
            raise ValueError(f"道具 #{pid} 不属于当前项目")
    shot.character_ids = cleaned
    shot.location_id = location_id
    shot.prop_ids = props
    shot.lock_version += 1
    existing = {b.character_id: b for b in db.query(ShotCharacterBinding).filter_by(shot_id=shot.id, owner_id=owner)}
    for cid in cleaned:
        item = existing.get(cid)
        if not item:
            item = ShotCharacterBinding(owner_id=owner, shot_id=shot.id, character_id=cid); db.add(item)
        item.variant_id = variants.get(cid)
        item.inheritance_source = "shot_override" if variants.get(cid) else "character_default"
    for cid, item in existing.items():
        if cid not in cleaned: db.delete(item)
    db.commit(); db.refresh(shot)


def selected_frames(db: Session, shot: Shot) -> dict[str,int]:
    result = {t.scope:t.resource_id for t in db.query(Take).filter_by(shot_id=shot.id, is_selected=True) if t.scope != "video"}
    if "start" not in result and shot.first_frame_resource_id: result["start"]=shot.first_frame_resource_id
    if "end" not in result and shot.last_frame_resource_id: result["end"]=shot.last_frame_resource_id
    return result


def checked_image_references(db: Session, owner: int, project_id: int, shot: Shot) -> list[dict]:
    """Images supplied to video generation, ordered exactly like checked workflow inputs."""
    orders=checked_orders(shot); frames=selected_frames(db,shot); draft=default_draft(shot); result=[]
    for frame in draft["frames"]:
        key=f"frame:{frame['id']}"; rid=frames.get(frame["id"])
        if frame.get("enabled",True) and rid and orders.get(key):
            label={"start":"首帧","end":"尾帧"}.get(frame["id"],f"关键帧 {frame['id']}")
            result.append({"resource_id":rid,"check_order":orders[key],"source":"frame","frame_kind":frame["id"],"label":f"已勾选{label}（{frame['time']}秒）","description":frame.get("prompt") or "以图片中的构图、人物姿态和场景状态为准","purpose":"约束对应时间点的画面构图与连续性"})
    for item in extras(db,owner,shot):
        if item["enabled"] and item["media_type"]=="image" and item["check_order"]:
            label=item["label"] or item["filename"] or f"素材 #{item['resource_id']}"
            result.append({"resource_id":item["resource_id"],"check_order":item["check_order"],"label":f"已勾选素材库图片「{label}」","description":f"参考文件 {item['filename']} 的可见内容","purpose":"作为视频画面参考，保持主体、造型或环境一致"})
    for asset in resources(db,owner,project_id,shot):
        if asset.get("enabled") and asset.get("resource_id"):
            result.append({"resource_id":asset["resource_id"],"check_order":asset.get("check_order") or 999999,"source":"context","label":f"已勾选{asset['name']}","description":asset.get("description") or "以参考图外观为准","purpose":"保持对应角色、场景或道具一致"})
    result.sort(key=lambda item:(item["check_order"],item["resource_id"]))
    unique=[]; seen=set()
    for item in result:
        if item["resource_id"] not in seen: unique.append(item);seen.add(item["resource_id"])
    return unique


def source_snapshot(db: Session, owner: int, project_id: int, shot: Shot, scope: str) -> dict:
    scene = db.get(Scene, shot.scene_id)
    project = project_service.owned_project(db, owner, project_id)
    draft = draft_with_defaults(db, owner, project_id, shot)
    snapshot = {"script":{k:getattr(shot,k) for k in ["visual_description","action","expression","dialogue","duration","camera_angle","camera_movement","composition","shot_size","source_story_version_id"]},
                "scene":scene.heading, "assets":resources(db,owner,project_id,shot), "extras":extras(db,owner,shot),
                "style":project.brief.visual_style if project.brief and hasattr(project.brief,"visual_style") else "",
                "ratio":project.brief.aspect_ratio if project.brief else ""}
    snapshot["script"]["dialogue"] = confirmed_manifest_dialogue(db,shot)
    if scope=="video": snapshot.update(prompt=draft["video_prompt"], frames=selected_frames(db,shot), video_settings={k:draft[k] for k in ["video_workflow_version_id","video_mode","video_params","prompt_inputs","prompt_asset_descriptions"]})
    else: snapshot["frame"] = next((f for f in draft["frames"] if f["id"]==scope), None)
    return snapshot


def shot_title(db: Session, shot: Shot, scene: Scene, episode: Episode) -> str:
    settings=shot.production_settings or {}
    if settings.get("title"): return settings["title"]
    manifest=db.query(ScriptManifestVersion).filter_by(episode_id=episode.id,status="confirmed").order_by(ScriptManifestVersion.id.desc()).first()
    if manifest:
        scenes=(manifest.content or {}).get("scenes") or []
        if 0 <= scene.sort_order < len(scenes):
            shots=scenes[scene.sort_order].get("shots") or []
            if 0 <= shot.sort_order < len(shots) and shots[shot.sort_order].get("title"): return shots[shot.sort_order]["title"]
    return settings.get("shot_title") or shot.visual_description or f"镜头 {shot.shot_no}"


def shot_view(db: Session, owner: int, project_id: int, shot_id: int) -> dict:
    shot, scene, episode, _ = context(db,owner,project_id,shot_id)
    takes = []
    fingerprints = {}
    for take in db.query(Take).filter_by(shot_id=shot.id).order_by(Take.take_no.desc()):
        resource = db.get(Resource,take.resource_id)
        if not resource or resource.deleted_at is not None: continue
        metadata = (take.generation_snapshot or {}).get("params", {}).get("__director", {})
        if take.scope not in fingerprints: fingerprints[take.scope] = digest(source_snapshot(db,owner,project_id,shot,take.scope))
        fingerprint = fingerprints[take.scope]
        takes.append({**production._take_out(db,take),"scope":take.scope,
                      "stale":bool(metadata.get("source_fingerprint") and metadata["source_fingerprint"]!=fingerprint)})
    tasks = []
    for link in db.query(ShotTaskLink).filter_by(shot_id=shot.id).order_by(ShotTaskLink.id.desc()):
        task = db.get(Task,link.task_id)
        if task:
            raw_params=task.params or {}; metadata=raw_params.get("__director",{})
            generation_service=metadata.get("generation_service") or ("gemini_image" if raw_params.get("__execution_provider")=="gemini_image" else "comfyui")
            reusable_params={k:deepcopy(v) for k,v in raw_params.items() if not k.startswith("__") and not (generation_service=="gemini_image" and k=="prompt")}
            tasks.append({"id":task.id,"status":task.status,"error":task.error,"scope":metadata.get("scope","video"),
                          "workflow_version_id":task.workflow_version_id,"generation_service":generation_service,
                          "provider_config_id":metadata.get("provider_config_id") or raw_params.get("__provider_config_id"),
                          "mode":metadata.get("mode") or "manual","params":reusable_params,
                          "sync_status":link.status,"sync_error":link.sync_error,"created_at":task.created_at})
    return {"id":shot.id,"scene_id":scene.id,"scene":scene.heading,"shot_no":shot.shot_no,"episode_id":episode.id,
            "title":shot_title(db,shot,scene,episode),
            "aspect_ratio":_.brief.aspect_ratio if _.brief else "9:16",
            "description":shot.visual_description,"action":shot.action,"dialogue":confirmed_manifest_dialogue(db,shot),"duration":total_duration(shot.duration,shot.production_settings or {}),
            "camera":shot.camera_movement,"revision":shot.lock_version,"draft":draft_with_defaults(db,owner,project_id,shot),
            "character_ids":shot.character_ids or [],"location_id":shot.location_id,"prop_ids":shot.prop_ids or [],
            "extras":extras(db,owner,shot),"check_orders":checked_orders(shot),
            "assets":resources(db,owner,project_id,shot),"takes":takes,"tasks":tasks,"selected_frames":selected_frames(db,shot)}


def overview(db: Session, owner: int, project_id: int, episode_id: int) -> dict:
    project_service.owned_project(db,owner,project_id)
    episode = db.query(Episode).filter_by(id=episode_id,project_id=project_id,owner_id=owner).first()
    if not episode: raise project_service.ProjectNotFoundError("分集不存在")
    shots = db.query(Shot).join(Scene,Scene.id==Shot.scene_id).filter(Scene.episode_id==episode_id,Shot.owner_id==owner).order_by(Scene.sort_order,Scene.id,Shot.sort_order,Shot.id).all()
    return {"episode_id":episode.id,"shots":[shot_view(db,owner,project_id,s.id) for s in shots]}


def visible(spec: dict, params: dict) -> bool:
    rule = spec.get("visible_when") or {}
    if rule:
        value=params.get(rule.get("key")); op=rule.get("operator")
        if op=="truthy" and not value: return False
        if op=="equals" and value!=rule.get("value"): return False
        if op=="not_equals" and value==rule.get("value"): return False
    reference = re.fullmatch(r"reference_image_(\d)", spec.get("key", ""))
    if reference and (not params.get("multi_reference_enabled") or int(reference[1]) > int(params.get("multi_reference_count") or 1)): return False
    return True


def compile_gemini_frame(db: Session, owner: int, project_id: int, shot_id: int, body: DirectorGenerate) -> dict:
    """Compile a frame into the existing Gemini queue; no Comfy workflow required."""
    from app.services import image_provider_service
    shot, scene, _, project = context(db, owner, project_id, shot_id)
    if body.scope == "video": raise ValueError("视频生成仅支持 ComfyUI")
    if body.workflow_version_id is not None: raise ValueError("Gemini Image 不使用 ComfyUI 工作流")
    frame = next((f for f in default_draft(shot)["frames"] if f["id"] == body.scope), None)
    if not frame: raise ValueError("关键帧不存在")
    provider = image_provider_service.get_enabled(db, body.provider_config_id)
    generation_type = db.query(GenerationType).filter_by(code="mixed", enabled=True, deleted_at=None).first()
    if not generation_type: raise ValueError("请先启用混合生图生成类型，以使用 Gemini Image 队列")
    if set(body.params) - {"size", "reference_resource_ids"}: raise ValueError("Gemini 图片参数包含未知字段")
    prompt = frame["prompt"].strip()
    if not prompt: raise ValueError("请先填写当前静态画面描述")
    assets = resources(db, owner, project_id, shot)
    prompt += "\n静态画面；" + {"start":"镜头动作起点", "end":"镜头动作终点", "key":"镜头中间转折状态"}[frame["kind"]]
    if assets: prompt += "\n画面实体：" + "；".join(a["name"] for a in assets)
    prompt += "\n构图：" + "；".join(filter(None, [shot.shot_size, shot.camera_angle, shot.composition]))
    if project.brief and project.brief.visual_style: prompt += "\n视觉风格：" + project.brief.visual_style
    prompt += "\nNegative：" + with_default_negative()
    reference_ids = body.params.get("reference_resource_ids", list(dict.fromkeys(a["resource_id"] for a in assets if a["resource_id"])))
    if not isinstance(reference_ids, list) or any(isinstance(r, bool) or not isinstance(r, int) for r in reference_ids):
        raise ValueError("参考图片必须为素材 ID 列表")
    size = body.params.get("size") or get_select_default(db, "image_size")
    sizes = [str(o["value"]) for o in get_select_options(db, "image_size") if o.get("value")]
    errors = []
    if not isinstance(size, str) or size not in sizes: errors.append("请选择系统维护项中的图片尺寸")
    for rid in reference_ids:
        if not db.query(Resource).filter_by(id=rid, owner_id=owner, media_type="image", deleted_at=None).first():
            errors.append(f"参考图片 #{rid} 不存在、已删除或无权访问")
    params = {"prompt":prompt, "size":size, "reference_resource_ids":reference_ids,
              "__execution_provider":"gemini_image", "__provider_config_id":provider.id}
    descriptor = {"name":f"Gemini Image · {provider.name} · {provider.model}", "mapping":{},
                  "generation_type_id":generation_type.id, "workflow_version_id":None,
                  "config_version_id":generation_type.published_config_version_id}
    snapshot = source_snapshot(db, owner, project_id, shot, body.scope)
    fingerprint = digest({"source":snapshot, "params":params, "provider":{
        "id":provider.id, "model":provider.model, "type":provider.provider, "endpoint":provider.base_url}})
    if body.expected_fingerprint and body.expected_fingerprint != fingerprint:
        raise Conflict("生成预检后镜头、素材或图片服务配置已更新，请重新检查")
    return {"params":params, "workflow":descriptor, "scope":body.scope, "errors":errors, "warnings":[],
            "input_resource_ids":reference_ids, "fingerprint":fingerprint,
            "source_fingerprint":digest(snapshot), "source_snapshot":snapshot}


def compile_generation(db: Session, owner: int, project_id: int, shot_id: int, body: DirectorGenerate) -> dict:
    shot, scene, _, project = context(db,owner,project_id,shot_id)
    if body.generation_service == "gemini_image": return compile_gemini_frame(db,owner,project_id,shot_id,body)
    if body.workflow_version_id is None: raise ValueError("请选择 ComfyUI 工作流")
    workflow=get_workflow(db,owner,project_id,body.workflow_version_id)
    expected_media="video" if body.scope=="video" else "image"
    if workflow["media_type"]!=expected_media: raise ValueError("工作流输出类型与制作目标不匹配")
    draft=default_draft(shot)
    frame=next((f for f in draft["frames"] if f["id"]==body.scope),None)
    if body.scope!="video" and not frame: raise ValueError("关键帧不存在")
    schema=deepcopy(workflow["parameters"]); mapping=dict(workflow["mapping"])
    if body.scope=="video":
        for spec in schema:
            if spec["key"] in {"prompt","duration"}: mapping.setdefault(spec["key"],spec["key"])
    for spec in schema:
        if spec.get("options_from"):
            if not spec.get("options"): spec["options"] = get_select_options(db, spec["options_from"])
            if spec.get("default") is None: spec["default"] = get_select_default(db, spec["options_from"])
    if body.scope=="video" and body.mode not in workflow["modes"]: raise ValueError("当前工作流不支持所选输入模式")
    assets=resources(db,owner,project_id,shot); frames=selected_frames(db,shot)
    if body.scope == "video":
        frames={f["id"]:frames[f["id"]] for f in draft["frames"] if f.get("enabled",True) and f["id"] in frames}
    prompt=(draft_with_defaults(db,owner,project_id,shot)["video_prompt"] if body.scope=="video" else frame["prompt"]).strip()
    if not prompt: raise ValueError("请先填写当前画面或视频描述")
    if body.scope!="video":
        prompt += "\n静态画面；" + {"start":"镜头动作起点","end":"镜头动作终点","key":"镜头中间转折状态"}[frame["kind"]]
    # Asset identity is carried by real image references, never the white-background asset-sheet prompt.
    if body.scope!="video":
        if assets: prompt += "\n画面实体：" + "；".join(a["name"] for a in assets)
        prompt += "\n构图：" + "；".join(filter(None,[shot.shot_size,shot.camera_angle,shot.composition]))
        if project.brief and getattr(project.brief,"visual_style",None): prompt += "\n视觉风格：" + project.brief.visual_style
    ratio=project.brief.aspect_ratio if project.brief else ""
    values={"prompt":prompt,"negative_prompt":with_default_negative(video_prompt_inputs(shot).get("negative_constraints")),
            "duration":total_duration(shot.duration,shot.production_settings or {}),"aspect_ratio":ratio,
            "first_frame":frames.get("start"),"last_frame":frames.get("end")}    # Checked context assets (characters / location / props) replace the blanket per-role fill:
    # image references now follow the shared check order instead of "every bound asset".
    for role in IMAGE_ROLES-{"first_frame","last_frame"}:
        values[role]=list(dict.fromkeys(a["resource_id"] for a in assets if a["resource_id"] and a.get("enabled",True) and (role=="reference_images" or a["role"]==role)))
    binding_errors=[]
    params={p["key"]:deepcopy(p.get("default")) for p in schema}
    # 宽高比/尺寸：剧本选择了横屏(16:9)或竖屏(9:16)时，尺寸类参数（width/height/size/
    # aspect_ratio/h3_aspect_ratio）自动对齐 brief 比例；未绑定时同样按默认填充。
    landscape = ratio.startswith("16:9") or ratio == "landscape"
    portrait = ratio.startswith("9:16")
    size_defaults = {"16:9": ("1920x1080", "16:9 (Widescreen)"), "9:16": ("1080x1920", "9:16 (Vertical)")}
    if landscape or portrait:
        want_size, want_label = size_defaults["16:9" if landscape else "9:16"]
        for spec in schema:
            key = spec["key"]
            if key in body.params or key in mapping: continue
            options = [str(o.get("value")) for o in (spec.get("options") or []) if o.get("value")]
            if key == "size":
                desired="16:9" if landscape else "9:16"
                match=next((v for v in options if v==desired),None) or next((v for v in options if v.startswith(desired+" ")),None)
                if match: params[key]=match
                elif not options: params[key]=desired
                elif want_size in options: params[key]=want_size
            elif key == "aspect_ratio" and (not options or ratio in options):
                params[key] = ratio
            elif key in {"width", "height"} and not options:
                width, height = (int(x) for x in want_size.split("x"))
                params[key] = width if key == "width" else height
    for spec in schema:
        role=mapping.get(spec["key"])
        if role not in values: continue
        value=values[role]
        if isinstance(value,list) and not spec.get("multiple"):
            if len(value)>1 and spec["key"] not in body.params: binding_errors.append(f"{spec.get('label') or spec['key']}只能接收单图，但镜头关联了多张参考；请选择具体素材或多图工作流")
            value=value[0] if len(value)==1 else None
        params[spec["key"]]=value
    known={p["key"] for p in schema}
    if any(k not in known and not (k.endswith("__mask") and k[:-6] in known) for k in body.params):
        raise ValueError("参数包含不属于当前工作流的字段")
    # Empty media controls mean automatic assignment, not an override with no resource.
    media_keys={p["key"] for p in schema if p.get("type") in {"image","audio","video"}}
    explicit={k:deepcopy(v) for k,v in body.params.items()
              if not (body.scope=="video" and k in media_keys and v in (None,"",[],0))}
    params.update(explicit)
    # Bindings and conventional Negative fields share the same mandatory baseline.
    # Explicit user text remains first; mandatory rules are appended once.
    for spec in schema:
        key = spec["key"]
        if mapping.get(key) == "negative_prompt" or key.lower() in {"negative", "negative_prompt"}:
            params[key] = with_default_negative(params.get(key))
    if body.scope=="video":
        ranks=checked_orders(shot)
        candidates=[(ranks.get(f"frame:{key}",0), "image", rid) for key,rid in frames.items()]
        candidates += [(e["check_order"],e["media_type"],e["resource_id"]) for e in extras(db,owner,shot) if e["enabled"]]
        candidates += [(a.get("check_order",0),"image",a["resource_id"]) for a in assets if a.get("enabled",True) and a["resource_id"]]
        candidates.sort(key=lambda item:item[0])
        pool={media:list(dict.fromkeys(rid for _,kind,rid in candidates if kind==media)) for media in ("image","audio","video")}
        # Reserve semantic and explicit assignments before filling remaining visible inputs.
        for spec in schema:
            key=spec["key"]; kind=spec.get("type")
            if kind not in pool or not visible(spec,params): continue
            if key not in explicit and not mapping.get(key): params[key]=None
            if params.get(key) in (None,"",[]): continue
            used=params[key] if isinstance(params[key],list) else [params[key]]
            pool[kind]=[rid for rid in pool[kind] if rid not in used]
        for spec in schema:
            key=spec["key"]; kind=spec.get("type")
            if kind not in pool or not visible(spec,params) or params.get(key) not in (None,"",[]): continue
            # If no adopted semantic reference exists, the checked resources can supply it.
            if body.mode=="first" and mapping.get(key)=="last_frame": continue
            available=pool[kind]
            if not available: continue
            count=(spec.get("max_items") or len(available)) if spec.get("multiple") else 1
            picked=available[:count]; pool[kind]=available[count:]
            params[key]=picked if spec.get("multiple") else picked[0]
    errors=binding_errors; warnings=[]
    if body.scope=="video":
        if body.mode=="first_last": required_roles={"first_frame","last_frame"}
        elif body.mode=="first": required_roles={"first_frame"}
        elif body.mode=="references": required_roles=set(mapping.values()) & (IMAGE_ROLES-{"first_frame","last_frame"})
        else: required_roles=set()
        for role in required_roles:
            key=next((k for k,v in mapping.items() if v==role),None)
            if not key or not params.get(key): errors.append(f"缺少视频输入：{role}")
        leftover=[rid for media in ("image","audio","video") for rid in pool.get(media,[])]
        if leftover: warnings.append(f"{len(leftover)} 个已勾选资源未匹配到工作流的图片/音频/视频输入项，已忽略；可手动绑定用途或更换工作流")
        if body.mode=="first" and "last_frame" in mapping.values():
            last_key=next(k for k,v in mapping.items() if v=="last_frame")
            if body.params.get(last_key): errors.append("首帧模式不能提交尾帧，请切换首尾帧模式")
            params[last_key]=None
        if confirmed_manifest_dialogue(db,shot):
            warnings.append("原剧本对白已保留；工作流音频能力未确认，当前按画面制作，需后期配音。")
            chars=sum(c.isalnum() for c in confirmed_manifest_dialogue(db,shot))
            if chars/5 > shot.duration: warnings.append("对白按每秒5字估算已超出镜头预算，请调整镜头或配音时长；未自动删改对白。")
    if not mapping.get(next((k for k,v in mapping.items() if v=="prompt"),"")):
        warnings.append("尚未绑定提示词用途，请手动填写工作流提示词，或先设置输入用途。")
    params={p["key"]:params.get(p["key"]) for p in schema if visible(p,params)}
    if body.scope == "video":
        for role in required_roles:
            key=next((k for k,v in mapping.items() if v==role),None)
            if key not in params: errors.append(f"视频必要输入 {role} 被条件隐藏，请检查工作流配置")
    inputs=[]
    for spec in schema:
        key=spec["key"]
        if key not in params: continue
        value=params[key]; kind=spec.get("type"); label=spec.get("label") or key
        if spec.get("required") and (value is None or value=="" or value==[] or isinstance(value,str) and not value.strip()): errors.append(f"请填写{label}")
        if value is None or value=="": continue
        if kind in {"int","float","slider","seed"}:
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value): errors.append(f"{label}必须是有效数值")
            elif kind in {"int","seed"} and int(value)!=value: errors.append(f"{label}必须是整数")
            elif spec.get("min") is not None and value<spec["min"] or spec.get("max") is not None and value>spec["max"]: errors.append(f"{label}超出工作流允许范围")
        if spec.get("options") and value not in [o["value"] for o in spec["options"]]: errors.append(f"{label}不在工作流允许选项中")
        if kind in {"image","video","audio"}:
            ids=value if isinstance(value,list) else [value]
            if isinstance(value, list):
                actual = next((p for p in db.get(WorkflowVersion,body.workflow_version_id).param_schema if p["key"] == key), {})
                try:
                    target, field = resolve_multimedia_target(db.get(WorkflowVersion,body.workflow_version_id).api_json, actual)
                    if not actual.get("multiple") or not isinstance(target.get(field), list): errors.append(f"{label}的节点未声明列表输入，请使用明确的多图工作流或独立图片字段")
                except Exception: errors.append(f"{label}的多素材节点映射无效")
            if isinstance(value,list)!=bool(spec.get("multiple")): errors.append(f"{label}单选/多选类型不匹配")
            if spec.get("max_items") and len(ids)>spec["max_items"]: errors.append(f"{label}超过参考数量上限")
            for rid in ids:
                if not isinstance(rid,int) or isinstance(rid,bool): errors.append(f"{label}必须引用素材 ID"); continue
                resource=db.query(Resource).filter_by(id=rid,owner_id=owner,media_type=kind,deleted_at=None).first()
                if not resource: errors.append(f"{label}素材不存在、已删除或无权访问")
                else: inputs.append(rid)
        if not production._mapping_exists(db.get(WorkflowVersion,body.workflow_version_id).api_json or {}, spec): errors.append(f"{label}没有有效节点映射")
    # Masks are optional image resources and must be validated as well.
    for key,value in body.params.items():
        if key.endswith("__mask") and value and params.get(key[:-6]):
            base=next(p for p in schema if p["key"]==key[:-6])
            resource=db.query(Resource).filter_by(id=value,owner_id=owner,media_type="image",deleted_at=None).first() if isinstance(value,int) else None
            if base.get("multiple"): errors.append("多素材输入暂不支持单张遮罩")
            if base.get("type")!="image" or not resource: errors.append("遮罩素材无效")
            else: params[key]=value;inputs.append(value)
    params={k:v for k,v in params.items() if v is not None and v!=""}
    snapshot=source_snapshot(db,owner,project_id,shot,body.scope)
    source_fingerprint=digest(snapshot)
    fingerprint=digest({"source":snapshot,"workflow":workflow,"params":params})
    if body.expected_fingerprint and body.expected_fingerprint!=fingerprint: raise Conflict("生成预检后镜头或素材已更新，请重新检查")
    if not errors:
        try: build_prompt(db.get(WorkflowVersion,body.workflow_version_id).api_json, db.get(WorkflowVersion,body.workflow_version_id).param_schema, params)
        except Exception as exc: errors.append(f"工作流参数编译失败：{exc}")
    return {"params":params,"workflow":workflow,"scope":body.scope,"errors":errors,"warnings":warnings,
            "input_resource_ids":list(dict.fromkeys(inputs)),"fingerprint":fingerprint,"source_fingerprint":source_fingerprint,"source_snapshot":snapshot}


def create_generation(db: Session, owner: int, project_id: int, shot_id: int, body: DirectorGenerate) -> dict:
    context(db,owner,project_id,shot_id)
    key=f"director:{shot_id}:{body.idempotency_key}"
    request_hash=digest(body.model_dump(exclude={"expected_fingerprint"}))
    existing=db.query(ShotTaskLink).filter_by(owner_id=owner,idempotency_key=key).first()
    if existing:
        task=db.get(Task,existing.task_id)
        if task.params.get("__director",{}).get("request_hash")!=request_hash: raise Conflict("同一提交标识不能用于不同参数")
        return {"task_id":task.id,"existing":True}
    compiled=compile_generation(db,owner,project_id,shot_id,body)
    if compiled["errors"]: raise ValueError("；".join(compiled["errors"]))
    workflow=compiled["workflow"]
    params=compiled["params"]
    params["__director"]={"scope":body.scope,"mode":body.mode,"generation_service":body.generation_service,"provider_config_id":body.provider_config_id,"shot_id":shot_id,"source_fingerprint":compiled["source_fingerprint"],
                            "source_snapshot":compiled["source_snapshot"],"request_hash":request_hash,"mapping":workflow["mapping"]}
    batch=Batch(user_id=owner,name=f"镜头 {shot_id} · {body.scope}",generation_type_id=workflow["generation_type_id"],workflow_version_id=workflow["workflow_version_id"],global_params={},source="short_drama",submitted_at=production._now())
    db.add(batch);db.flush()
    task=Task(user_id=owner,batch_id=batch.id,row_no=0,generation_type_id=workflow["generation_type_id"],workflow_version_id=workflow["workflow_version_id"],
              config_version_id=workflow["config_version_id"],params=params,status="PENDING")
    db.add(task);db.flush()
    db.add(ShotTaskLink(owner_id=owner,shot_id=shot_id,task_id=task.id,purpose="director",status="linked",idempotency_key=key))
    production._audit(db,owner,"short_drama.director.generate",project_id,f"shot={shot_id};scope={body.scope};task={task.id}")
    try: db.commit()
    except IntegrityError:
        db.rollback()
        existing=db.query(ShotTaskLink).filter_by(owner_id=owner,idempotency_key=key).first()
        if not existing: raise
        task=db.get(Task,existing.task_id)
        if task.params.get("__director",{}).get("request_hash")!=request_hash: raise Conflict("重复提交参数不一致")
        return {"task_id":task.id,"existing":True}
    return {"task_id":task.id,"existing":False}


def import_frame(db: Session, owner: int, project_id: int, shot_id: int, scope: str, resource_id: int) -> None:
    shot,*_=context(db,owner,project_id,shot_id)
    if not any(f["id"]==scope for f in default_draft(shot)["frames"]): raise ValueError("关键帧不存在")
    resource=db.query(Resource).filter_by(id=resource_id,owner_id=owner,media_type="image",deleted_at=None).first()
    if not resource: raise ValueError("图片素材不存在或无访问权限")
    number=(db.query(func.max(Take.take_no)).filter_by(shot_id=shot.id).scalar() or 0)+1
    snapshot=source_snapshot(db,owner,project_id,shot,scope)
    db.add(Take(owner_id=owner,shot_id=shot.id,scope=scope,resource_id=resource_id,take_no=number,status="candidate",
                generation_snapshot={"source":"library","params":{"__director":{"scope":scope,"source_fingerprint":digest(snapshot)}}}))
    db.commit()


def adopt(db: Session, owner: int, project_id: int, take_id: int) -> None:
    take=production._owned_take(db,owner,project_id,take_id)
    resource=db.query(Resource).filter_by(id=take.resource_id,owner_id=owner,deleted_at=None).first()
    if not resource or resource.media_type!=("video" if take.scope=="video" else "image"): raise ValueError("候选素材类型错误或已删除")
    shot,*_=context(db,owner,project_id,take.shot_id)
    if take.scope!="video" and not any(f["id"]==take.scope for f in default_draft(shot)["frames"]): raise ValueError("对应帧已移除，不能采用")
    if take.is_selected: return
    result=db.execute(update(Shot).where(Shot.id==shot.id,Shot.lock_version==shot.lock_version).values(lock_version=shot.lock_version+1))
    if result.rowcount != 1: raise Conflict("镜头采用状态已更新，请重新载入后再采用")
    db.query(Take).filter(Take.shot_id==take.shot_id,Take.scope==take.scope,Take.is_selected.is_(True)).update({Take.is_selected:False,Take.status:"candidate"},synchronize_session=False)
    db.flush(); take.is_selected=True;take.status="selected"
    if take.scope=="start": shot.first_frame_resource_id=take.resource_id
    if take.scope=="end": shot.last_frame_resource_id=take.resource_id
    db.commit()
