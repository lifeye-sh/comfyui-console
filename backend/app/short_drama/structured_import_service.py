"""Deterministic import for script, asset-prompt and video-prompt Markdown."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import Character, CharacterVariant, Episode, Location, ProjectAssetVersion
from app.models import Prop, Scene, ShortDramaProject, Shot, StructuredDramaImport
from app.short_drama.dialogue import dialogue_spans
from app.short_drama.skill_contracts import SKILL_ID, SKILL_VERSION, SCHEMA_VERSION

DataType = Literal["script", "assets", "video_prompts"]


class StructuredImportError(ValueError):
    pass


def _text(value: str) -> str:
    return value.strip().replace("\r\n", "\n")


def _section(block: str, name: str) -> str:
    match = re.search(rf"【{re.escape(name)}】：\s*(.*?)(?=\n【[^\n]+】：|\Z)", block, re.S)
    return _text(match.group(1)) if match else ""


def _coverage(value: str) -> list[int]:
    if "全组" in value:
        return list(range(1, 25))
    result: set[int] = set()
    for start, end in re.findall(r"组?(\d+)(?:\s*[~～-]\s*(\d+))?", value):
        first, last = int(start), int(end or start)
        result.update(range(min(first, last), max(first, last) + 1))
    return sorted(result)


def parse_script(content: str) -> dict[str, Any]:
    title = re.search(r"^#\s+《([^》]+)》", content, re.M)
    duration = re.search(r"总时长\s*(\d+)s", content)
    aspect = re.search(r"(\d+:\d+)\s*横屏", content)
    characters = []
    section = re.search(r"### 5\.2.*?\n(.*?)(?=\n### 5\.3)", content, re.S)
    if section:
        block = section.group(1)
        marks = list(re.finditer(r"^\*\*@([^*]+)\*\*（([A-Z])\s*级）\s*$", block, re.M))
        for index, mark in enumerate(marks):
            end = marks[index + 1].start() if index + 1 < len(marks) else len(block)
            characters.append({"name": mark.group(1).strip(), "description": _text(block[mark.end():end])})

    scenes = []
    pattern = re.compile(
        r"^### 场\s*(\d+)\s*[　 ]*(.*?)（(\d+)~(\d+)s\s*·\s*(\d+)\s*组）\s*\n"
        r"(.*?)(?=^---\s*$\n\s*### 场|\Z)", re.M | re.S,
    )
    for match in pattern.finditer(content):
        body = _text(match.group(6))
        heading = _text(match.group(2))
        location = re.search(r"(内景|外景)\s*·\s*(.*?)\s*-\s*(日|夜)", heading)
        people = re.search(r"出场人物：([^\n]+)", body)
        shots = []
        marks = list(re.finditer(r"◆组(\d+)", body))
        for index, mark in enumerate(marks):
            end = marks[index + 1].start() if index + 1 < len(marks) else len(body)
            value = _text(body[mark.start():end])
            times = list(re.finditer(r"（(\d+)~(\d+)s）", body[max(0, mark.start() - 80):mark.start()]))
            shots.append({
                "shot_no": int(mark.group(1)), "content": value,
                "start": int(times[-1].group(1)) if times else None,
                "end": int(times[-1].group(2)) if times else None,
            })
        scenes.append({
            "scene_no": int(match.group(1)), "heading": heading,
            "start": int(match.group(3)), "end": int(match.group(4)),
            "expected_shots": int(match.group(5)), "content": body, "shots": shots,
            "interior_exterior": location.group(1) if location else "",
            "location_name": location.group(2).strip() if location else heading,
            "time_of_day": location.group(3) if location else "",
            "characters": [x.strip().lstrip("@") for x in people.group(1).split("、")] if people else [],
        })
    prop_names = ["损坏的细肩带织物", "缎面五瓣小花", "便携针线包", "工作人员对讲机", "四球冰激凌杯", "冰激凌勺", "纸巾", "翻开的化妆包", "两把金属折叠椅", "倒计时牌"]
    props = [name for name in prop_names if any(word in content for word in name.replace("工作人员", "").replace("四球", "").split())]
    return {
        "data_type": "script", "title": title.group(1) if title else "",
        "duration": int(duration.group(1)) if duration else 0,
        "aspect_ratio": aspect.group(1) if aspect else "", "characters": characters,
        "scenes": scenes, "props": props,
        "counts": {"characters": len(characters), "scenes": len(scenes), "shots": sum(len(x["shots"]) for x in scenes), "props": len(props)},
    }


def parse_assets(content: str) -> dict[str, Any]:
    assets = []
    pattern = re.compile(r"^###\s+[🎭🏠]\s+(A-\d+|S-\d+)｜@?([^\n（]+)([^\n]*)\n(.*?)(?=^###\s+[🎭🏠]|^##\s+三、|\Z)", re.M | re.S)
    for match in pattern.finditer(content):
        prompt = re.search(r"```text\s*\n(.*?)\n```", match.group(4), re.S)
        key = match.group(1)
        assets.append({"external_key": key, "asset_type": "character" if key.startswith("A-") else "location", "name": match.group(2).strip(), "label": _text(match.group(2) + match.group(3)), "prompt": _text(prompt.group(1) if prompt else match.group(4)), "coverage": []})
    mappings = {key: {"text": _text(value), "shots": _coverage(value)} for key, value in re.findall(r"^\|\s*(A-\d+|S-\d+)\s+[^|]*\|\s*([^|]+)\|", content, re.M)}
    for asset in assets:
        asset.update({"coverage": mappings.get(asset["external_key"], {}).get("shots", []), "coverage_text": mappings.get(asset["external_key"], {}).get("text", "")})
    suffix = re.search(r"通用后缀.*?`([^`]+)`", content)
    return {"data_type": "assets", "common_suffix": suffix.group(1) if suffix else "", "assets": assets, "counts": {"character_assets": sum(x["asset_type"] == "character" for x in assets), "location_assets": sum(x["asset_type"] == "location" for x in assets), "total": len(assets)}}


def parse_video(content: str) -> dict[str, Any]:
    scene_for_group: dict[int, int] = {}
    scenes = list(re.finditer(r"^## 场\s*(\d+).*?$", content, re.M))
    for index, mark in enumerate(scenes):
        end = scenes[index + 1].start() if index + 1 < len(scenes) else len(content)
        for number in re.findall(r"^### ◆组(\d+)", content[mark.end():end], re.M):
            scene_for_group[int(number)] = int(mark.group(1))
    groups = []
    pattern = re.compile(r"^### ◆组(\d+)｜(\d+)~(\d+)s｜(\d+)s[^\n]*\n\s*```text\s*\n(.*?)\n```", re.M | re.S)
    for match in pattern.finditer(content):
        prompt = _text(match.group(5)); timeline = _section(prompt, "时间轴分镜")
        groups.append({
            "shot_no": int(match.group(1)), "scene_no": scene_for_group.get(int(match.group(1))),
            "start": int(match.group(2)), "end": int(match.group(3)), "duration": int(match.group(4)),
            "style": _section(prompt, "画幅风格"), "scene_asset": _section(prompt, "场景资产"),
            "core_characters": _section(prompt, "核心人物"), "negative_prompt": _section(prompt, "负面排除"),
            "timeline_storyboard": timeline, "continuity": _section(prompt, "接续状态"),
            "dialogue": "\n".join(
                f"{item['speaker']}：{item['text']}" if item.get("speaker") else item["text"]
                for item in dialogue_spans(timeline)
            ) or "\n".join(re.findall(r"台词：【(.*?)】", timeline)), "prompt": prompt,
        })
    appendix = re.search(r"^## 附 A.*", content, re.M | re.S)
    return {"data_type": "video_prompts", "groups": groups, "appendices": _text(appendix.group(0)) if appendix else "", "counts": {"shots": len(groups), "timeline_shots": sum(len(re.findall(r"^\d\d:\d\d-\d\d:\d\d \[镜头\d+\]", x["timeline_storyboard"], re.M)) for x in groups), "continuity": sum(bool(x["continuity"]) for x in groups)}}


def parse_content(data_type: DataType, content: str) -> dict[str, Any]:
    normalized = content.replace("\r\n", "\n").lstrip("\ufeff")
    parsed = parse_script(normalized) if data_type == "script" else parse_assets(normalized) if data_type == "assets" else parse_video(normalized)
    expected = parsed.get("scenes") if data_type == "script" else parsed.get("assets") if data_type == "assets" else parsed.get("groups")
    if not expected:
        raise StructuredImportError("文件结构无法识别，请确认选择了正确的数据类型")
    return parsed


def _project(db: Session, owner_id: int, project_id: int) -> ShortDramaProject:
    item = db.query(ShortDramaProject).filter(ShortDramaProject.id == project_id, ShortDramaProject.owner_id == owner_id, ShortDramaProject.deleted_at.is_(None)).first()
    if not item:
        raise StructuredImportError("短剧项目不存在")
    return item


def _ref(import_id: int, key: str) -> dict[str, Any]:
    return {"structured_import_id": import_id, "external_key": key}


def _character(db: Session, owner_id: int, project_id: int, name: str, description: str, import_id: int) -> Character:
    item = db.query(Character).filter(Character.project_id == project_id, Character.name == name).first()
    if not item:
        item = Character(owner_id=owner_id, project_id=project_id, name=name); db.add(item)
    item.aliases = list(dict.fromkeys([*(item.aliases or []), f"@{name}"]))
    item.appearance = description or item.appearance; item.age_appearance = item.age_appearance or "成年"
    item.source_references = [*(item.source_references or []), _ref(import_id, f"character:{name}")]
    db.flush(); return item


def _apply_script(db: Session, owner_id: int, project: ShortDramaProject, record: StructuredDramaImport) -> dict[str, int]:
    data = record.parsed_data
    episode = db.query(Episode).filter(Episode.project_id == project.id, Episode.number == 1).first()
    if not episode:
        episode = Episode(owner_id=owner_id, project_id=project.id, number=1, title="第 1 集", sort_order=0); db.add(episode)
    episode.target_duration = data.get("duration") or 300; episode.script_mode = "storyboard"; episode.script_text = record.content
    episode.script_settings = {"structured_import_id": record.id, "aspect_ratio": data.get("aspect_ratio", ""),
        "director_skill": {"id": SKILL_ID, "version": SKILL_VERSION, "schema_version": SCHEMA_VERSION}}
    project.source_type = "script"; project.settings = {**(project.settings or {}), "structured_import_batch": record.batch_key,
        "director_skill": {"id": SKILL_ID, "version": SKILL_VERSION, "schema_version": SCHEMA_VERSION}}; db.flush()
    people = {value["name"]: _character(db, owner_id, project.id, value["name"], value["description"], record.id) for value in data["characters"]}
    for name in ("工作人员", "老板", "粉丝群像"):
        if name in record.content: people[name] = _character(db, owner_id, project.id, name, "辅助、画外或群像角色，不要求生成清晰人脸。", record.id)
    for name in data["props"]:
        prop = db.query(Prop).filter(Prop.project_id == project.id, Prop.name == name).first()
        if not prop: prop = Prop(owner_id=owner_id, project_id=project.id, name=name); db.add(prop)
        context_match = re.search(rf"[^。！？\n]{{0,50}}{re.escape(name)}[^。！？\n]{{0,80}}", record.content)
        prop.description = _text(context_match.group(0)) if context_match else f"剧本中的{name}"
        prop.source_references = [_ref(record.id, f"prop:{name}")]
    count = 0
    for value in data["scenes"]:
        scene = db.query(Scene).filter(Scene.episode_id == episode.id, Scene.scene_no == str(value["scene_no"])).first()
        if not scene: scene = Scene(owner_id=owner_id, episode_id=episode.id, scene_no=str(value["scene_no"])); db.add(scene)
        scene.heading = value["heading"]; scene.location_name = value["location_name"]; scene.time_of_day = value["time_of_day"]; scene.interior_exterior = value["interior_exterior"]
        scene.content = value["content"]; scene.purpose = value["heading"]; scene.target_duration = value["end"] - value["start"]; scene.sort_order = value["scene_no"]
        scene.character_ids = [people[name].id for name in value["characters"] if name in people]; scene.source_references = [_ref(record.id, f"scene:{value['scene_no']}")]; db.flush()
        for shot_value in value["shots"]:
            shot = db.query(Shot).filter(Shot.scene_id == scene.id, Shot.shot_no == shot_value["shot_no"]).first()
            if not shot: shot = Shot(owner_id=owner_id, scene_id=scene.id, shot_no=shot_value["shot_no"]); db.add(shot)
            shot.visual_description = shot_value["content"]; shot.action = ""
            shot.dialogue = "\n".join(
                f"{line['speaker']}：{line['text']}" if line.get("speaker") else line["text"]
                for line in dialogue_spans(shot_value["content"], people.keys())
            )
            shot.character_ids = scene.character_ids; shot.sort_order = shot_value["shot_no"]
            shot.duration = max(.1, (shot_value["end"] - shot_value["start"]) if shot_value["start"] is not None else scene.target_duration / max(1, value["expected_shots"]))
            shot.production_settings = {**(shot.production_settings or {}), "external_key": f"group:{shot_value['shot_no']:02d}", "episode_start": shot_value["start"], "episode_end": shot_value["end"], "structured_import_id": record.id}; count += 1
    return {"episodes": 1, "scenes": len(data["scenes"]), "shots": count, "characters": len(people), "props": len(data["props"])}


def _version(db: Session, owner_id: int, project_id: int, entity_type: str, entity_id: int, value: dict[str, Any], record: StructuredDramaImport) -> None:
    versions = db.query(ProjectAssetVersion).filter(ProjectAssetVersion.project_id == project_id, ProjectAssetVersion.entity_type == entity_type, ProjectAssetVersion.entity_id == entity_id).all()
    item = next((x for x in versions if (x.generation_snapshot or {}).get("external_key") == value["external_key"]), None)
    if not item: item = ProjectAssetVersion(owner_id=owner_id, project_id=project_id, entity_type=entity_type, entity_id=entity_id, version=max((x.version for x in versions), default=0) + 1); db.add(item)
    item.prompt = value["prompt"]; item.generation_snapshot = {"external_key": value["external_key"], "coverage_shots": value["coverage"], "common_suffix": record.parsed_data["common_suffix"], "structured_import_id": record.id, "generation_status": "not_generated"}; db.flush()


def _apply_assets(db: Session, owner_id: int, project: ShortDramaProject, record: StructuredDramaImport) -> dict[str, int]:
    locations: dict[str, Location] = {}; counts = {"character_assets": 0, "location_assets": 0}
    location_names = {"化妆间": "俱乐部化妆间", "走廊化妆间外": "化妆间外走廊", "见面会舞台": "见面会舞台", "冰激凌店": "老街冰激凌店"}
    for value in record.parsed_data["assets"]:
        key = value["external_key"]
        if value["asset_type"] == "character":
            person = _character(db, owner_id, project.id, "叶修" if key == "A-1" else "苏沐橙", "", record.id)
            look = "深灰休闲装" if key == "A-1" else "浅粉礼裙版" if key == "A-2" else "奶油色卫衣版"
            variant = db.query(CharacterVariant).filter(CharacterVariant.character_id == person.id, CharacterVariant.name == look).first()
            if not variant: variant = CharacterVariant(owner_id=owner_id, character_id=person.id, name=look, version=1); db.add(variant)
            variant.description = value.get("label") or look
            variant.wardrobe = ""; variant.hairstyle = ""; variant.makeup = ""
            variant.is_default = key in {"A-1", "A-2"}; variant.source_references = [_ref(record.id, key)]; db.flush(); _version(db, owner_id, project.id, "variant", variant.id, value, record); counts["character_assets"] += 1
        else:
            name = location_names.get(value["name"], value["name"]); location = db.query(Location).filter(Location.project_id == project.id, Location.name == name).first()
            if not location: location = Location(owner_id=owner_id, project_id=project.id, name=name); db.add(location)
            location.description = value.get("label") or name
            location.spatial_layout = ""; location.time_weather = ""; location.lighting = ""; location.source_references = [_ref(record.id, key)]; db.flush(); locations[key] = location; _version(db, owner_id, project.id, "location", location.id, value, record); counts["location_assets"] += 1
    episode = db.query(Episode).filter(Episode.project_id == project.id, Episode.number == 1).first()
    if episode:
        shots = db.query(Shot).join(Scene).filter(Scene.episode_id == episode.id).all(); by_no = {x.shot_no: x for x in shots}
        for value in record.parsed_data["assets"]:
            location = locations.get(value["external_key"])
            if location:
                for number in value["coverage"]:
                    if number in by_no: by_no[number].location_id = location.id; by_no[number].production_settings = {**(by_no[number].production_settings or {}), "scene_asset_key": value["external_key"]}
        for scene in episode.scenes:
            located = next((x for x in shots if x.scene_id == scene.id and x.location_id), None)
            if located: scene.location_id = located.location_id
    return counts


def _apply_video(db: Session, project: ShortDramaProject, record: StructuredDramaImport) -> dict[str, int]:
    episode = db.query(Episode).filter(Episode.project_id == project.id, Episode.number == 1).first()
    if not episode: raise StructuredImportError("请先导入剧本数据文件")
    shots = db.query(Shot).join(Scene).filter(Scene.episode_id == episode.id).all(); by_no = {x.shot_no: x for x in shots}; missing = []
    for value in record.parsed_data["groups"]:
        shot = by_no.get(value["shot_no"])
        if not shot: missing.append(value["shot_no"]); continue
        shot.duration = value["duration"]; shot.timeline_storyboard = value["timeline_storyboard"]; shot.video_prompt = value["prompt"]; shot.negative_prompt = value["negative_prompt"]; shot.continuity = value["continuity"]; shot.dialogue = value["dialogue"] or shot.dialogue
        shot.production_settings = {**(shot.production_settings or {}), "episode_start": value["start"],
            "episode_end": value["end"], "original_platform": "seedance_2",
            "director_prompt_layers": {"director": "video_prompt", "model_adapter": "seedance_2", "execution": None},
            "structured_video_import_id": record.id}
    if missing: raise StructuredImportError(f"以下组号未找到对应Shot：{missing}")
    return {"shots": len(by_no)}


def apply_import(db: Session, owner_id: int, project_id: int, data_type: DataType, filename: str, content: str, batch_key: str | None = None) -> tuple[StructuredDramaImport, dict[str, int], bool]:
    project = _project(db, owner_id, project_id); normalized = content.replace("\r\n", "\n").lstrip("\ufeff"); checksum = hashlib.sha256(normalized.encode()).hexdigest()
    record = db.query(StructuredDramaImport).filter(StructuredDramaImport.project_id == project_id, StructuredDramaImport.data_type == data_type, StructuredDramaImport.checksum == checksum).first()
    if record and record.status == "applied": return record, record.parsed_data.get("applied_counts", {}), True
    parsed = parse_content(data_type, normalized)
    if not record: record = StructuredDramaImport(owner_id=owner_id, project_id=project_id, batch_key=batch_key or f"batch-{uuid4().hex[:12]}", data_type=data_type, filename=filename, checksum=checksum, content=normalized); db.add(record)
    record.parsed_data = parsed; record.status = "applying"; db.flush()
    if data_type != "script" and not db.query(StructuredDramaImport).filter(StructuredDramaImport.project_id == project_id, StructuredDramaImport.data_type == "script", StructuredDramaImport.status == "applied").first(): raise StructuredImportError("请先导入并应用剧本数据文件")
    if data_type == "video_prompts" and not db.query(StructuredDramaImport).filter(StructuredDramaImport.project_id == project_id, StructuredDramaImport.data_type == "assets", StructuredDramaImport.status == "applied").first(): raise StructuredImportError("请先导入并应用资产提示词数据文件")
    counts = _apply_script(db, owner_id, project, record) if data_type == "script" else _apply_assets(db, owner_id, project, record) if data_type == "assets" else _apply_video(db, project, record)
    record.parsed_data = {**parsed, "applied_counts": counts}; record.status = "applied"; db.commit(); db.refresh(record); return record, counts, False


def list_imports(db: Session, owner_id: int, project_id: int) -> list[StructuredDramaImport]:
    _project(db, owner_id, project_id)
    return db.query(StructuredDramaImport).filter(StructuredDramaImport.project_id == project_id, StructuredDramaImport.owner_id == owner_id).order_by(StructuredDramaImport.created_at).all()
