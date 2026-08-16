"""Scene-to-shot suggestions and manually controlled storyboard editing."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AuditLog, Character, Episode, Location, Prop, Resource, Scene, ShortDramaProject,
    Shot, StoryboardCandidate, StoryVersion,
)
from app.schemas.short_drama import ShotBulkPatchIn, ShotInput, ShotPatchIn
from app.short_drama import project_service


class StoryboardValidationError(ValueError): pass


def _now() -> datetime: return datetime.now(UTC).replace(tzinfo=None)


def _audit(db: Session, owner_id: int, action: str, project_id: int, detail: str = "") -> None:
    db.add(AuditLog(user_id=owner_id, action=action, target_type="short_drama_project", target_id=project_id, detail=detail or None))


def _owned_scene(db: Session, owner_id: int, project_id: int, scene_id: int) -> Scene:
    scene = db.query(Scene).join(Episode, Episode.id == Scene.episode_id).filter(
        Scene.id == scene_id, Scene.owner_id == owner_id, Episode.project_id == project_id,
    ).first()
    if not scene: raise project_service.ProjectNotFoundError("场景不存在")
    return scene


def _owned_shot(db: Session, owner_id: int, project_id: int, shot_id: int) -> Shot:
    item = db.query(Shot).join(Scene, Scene.id == Shot.scene_id).join(Episode, Episode.id == Scene.episode_id).filter(
        Shot.id == shot_id, Shot.owner_id == owner_id, Episode.project_id == project_id,
    ).first()
    if not item: raise project_service.ProjectNotFoundError("镜头不存在")
    return item


def _version(db: Session, owner_id: int, project_id: int, version_id: int | None) -> StoryVersion:
    query = db.query(StoryVersion).filter(StoryVersion.owner_id == owner_id, StoryVersion.project_id == project_id)
    item = query.filter(StoryVersion.id == version_id).first() if version_id else query.filter(StoryVersion.is_current.is_(True)).first()
    if not item: raise StoryboardValidationError("请先确认或保存一个剧本版本")
    return item


def _snapshot_scene(scene: Scene, version: StoryVersion) -> dict[str, Any]:
    for episode in (version.content or {}).get("episodes", []):
        for item in episode.get("scenes", []):
            if item.get("id") == scene.id or (item.get("scene_no") == scene.scene_no and episode.get("id") == scene.episode_id):
                return item
    episodes = (version.content or {}).get("episodes", [])
    episode_index = max(0, (scene.episode.number if scene.episode else 1) - 1)
    active_scenes = sorted(list(scene.episode.scenes if scene.episode else []), key=lambda item: (item.sort_order, item.id))
    scene_index = next((index for index, item in enumerate(active_scenes) if item.id == scene.id), -1)
    if episode_index < len(episodes) and 0 <= scene_index < len(episodes[episode_index].get("scenes", [])):
        return episodes[episode_index]["scenes"][scene_index]
    raise StoryboardValidationError("指定剧本版本中找不到该场景")


def _duration_target(db: Session, scene: Scene) -> float:
    if scene.target_duration > 0: return float(scene.target_duration)
    episode = db.get(Episode, scene.episode_id)
    scene_count = db.query(func.count(Scene.id)).filter(Scene.episode_id == scene.episode_id).scalar() or 1
    return max(1.0, float(episode.target_duration if episode else 60) / scene_count)


def create_candidate(db: Session, owner_id: int, project_id: int, scene_id: int, version_id: int | None) -> StoryboardCandidate:
    project_service.owned_project(db, owner_id, project_id); scene = _owned_scene(db, owner_id, project_id, scene_id); version = _version(db, owner_id, project_id, version_id)
    source = _snapshot_scene(scene, version); elements = list(source.get("elements") or [])
    if not elements:
        elements = [{"type": "action", "text": source.get("content") or source.get("heading") or "场景建立"}]
    target = _duration_target(db, scene); count = len(elements); base_duration = round(target / count, 2)
    names = {item.name: item.id for item in db.query(Character).filter(Character.owner_id == owner_id, Character.project_id == project_id).all()}
    props = db.query(Prop).filter(Prop.owner_id == owner_id, Prop.project_id == project_id).all()
    sizes = ("全景", "中景", "近景", "特写")
    shots: list[dict[str, Any]] = []
    for index, element in enumerate(elements):
        text = str(element.get("text", "")).strip(); element_type = element.get("type", "action")
        speaker = str(element.get("speaker", "")).strip(); character_ids = [names[speaker]] if speaker in names else list(source.get("character_ids") or scene.character_ids or [])
        prop_ids = [item.id for item in props if item.name and item.name in text]
        shots.append({
            "purpose": "推进对白" if element_type == "dialogue" else "呈现场景动作",
            "visual_description": text, "action": text if element_type != "dialogue" else "", "expression": "",
            "dialogue": f"{speaker}：{text}" if element_type == "dialogue" and speaker else (text if element_type == "dialogue" else ""),
            "character_ids": character_ids, "location_id": source.get("location_id") or scene.location_id, "prop_ids": prop_ids,
            "mood": "", "shot_size": sizes[index % len(sizes)], "camera_angle": "平视", "camera_movement": "固定",
            "composition": "主体居中", "transition": "切", "duration": base_duration,
            "first_frame_resource_id": None, "last_frame_resource_id": None, "pose_resource_id": None,
            "reference_video_resource_id": None, "reference_audio_resource_id": None, "reference_resource_ids": [],
            "status": "draft", "production_settings": {},
        })
    if shots: shots[-1]["duration"] = round(target - sum(item["duration"] for item in shots[:-1]), 2)
    warnings: list[dict[str, Any]] = []
    existing_ready = db.query(func.count(Shot.id)).filter(Shot.scene_id == scene.id, Shot.status == "ready").scalar() or 0
    if existing_ready: warnings.append({"code": "confirmed_preserved", "message": f"重新拆镜时将保留 {existing_ready} 个已确认镜头"})
    if abs(sum(item["duration"] for item in shots) - target) > 0.1: warnings.append({"code": "duration_mismatch", "message": "镜头总时长与场景目标时长不一致"})
    candidate = StoryboardCandidate(owner_id=owner_id, project_id=project_id, scene_id=scene.id, story_version_id=version.id, status="pending", payload={"shots": shots, "target_duration": target, "existing_shots": db.query(func.count(Shot.id)).filter(Shot.scene_id == scene.id).scalar() or 0}, validation_warnings=warnings)
    db.add(candidate); _audit(db, owner_id, "short_drama.storyboard.preview", project_id, f"scene={scene.id};version={version.id}"); db.commit(); db.refresh(candidate); return candidate


def _candidate(db: Session, owner_id: int, project_id: int, candidate_id: int) -> StoryboardCandidate:
    item = db.query(StoryboardCandidate).filter(StoryboardCandidate.id == candidate_id, StoryboardCandidate.owner_id == owner_id, StoryboardCandidate.project_id == project_id).first()
    if not item: raise project_service.ProjectNotFoundError("拆镜候选不存在")
    return item


def _renumber(db: Session, scene_id: int) -> None:
    items = db.query(Shot).filter(Shot.scene_id == scene_id).order_by(Shot.sort_order, Shot.id).all()
    for index, item in enumerate(items): item.shot_no = -(index + 1)
    db.flush()
    for index, item in enumerate(items): item.shot_no = index + 1; item.sort_order = index
    db.flush()


def confirm_candidate(db: Session, owner_id: int, project_id: int, candidate_id: int, mode: str) -> StoryboardCandidate:
    project_service.owned_project(db, owner_id, project_id); item = _candidate(db, owner_id, project_id, candidate_id)
    if item.status == "confirmed": return item
    if item.status != "pending": raise StoryboardValidationError("该拆镜候选不能确认")
    _owned_scene(db, owner_id, project_id, item.scene_id)
    if mode == "replace_drafts":
        db.query(Shot).filter(Shot.scene_id == item.scene_id, Shot.owner_id == owner_id, Shot.status == "draft").delete(synchronize_session=False); db.flush()
        _renumber(db, item.scene_id)
    existing = db.query(Shot).filter(Shot.scene_id == item.scene_id).order_by(Shot.sort_order, Shot.id).all()
    for offset, data in enumerate((item.payload or {}).get("shots", [])):
        db.add(Shot(owner_id=owner_id, scene_id=item.scene_id, source_story_version_id=item.story_version_id, shot_no=len(existing)+offset+1, sort_order=len(existing)+offset, **data))
    db.flush(); _renumber(db, item.scene_id); item.status = "confirmed"; item.confirmed_mode = mode; item.confirmed_at = _now()
    _audit(db, owner_id, "short_drama.storyboard.confirm", project_id, f"candidate={item.id};mode={mode}"); db.commit(); db.refresh(item); return item


def _validate_refs(db: Session, owner_id: int, project_id: int, data: ShotInput) -> None:
    if data.character_ids:
        ids = {row[0] for row in db.query(Character.id).filter(Character.owner_id == owner_id, Character.project_id == project_id, Character.id.in_(data.character_ids)).all()}
        if ids != set(data.character_ids): raise StoryboardValidationError("镜头引用了不存在的角色")
    if data.location_id and not db.query(Location.id).filter(Location.id == data.location_id, Location.owner_id == owner_id, Location.project_id == project_id).first(): raise StoryboardValidationError("镜头引用了不存在的地点")
    if data.prop_ids:
        ids = {row[0] for row in db.query(Prop.id).filter(Prop.owner_id == owner_id, Prop.project_id == project_id, Prop.id.in_(data.prop_ids)).all()}
        if ids != set(data.prop_ids): raise StoryboardValidationError("镜头引用了不存在的道具")
    resource_ids = set(data.reference_resource_ids)
    resource_ids.update(value for value in (data.first_frame_resource_id, data.last_frame_resource_id, data.pose_resource_id, data.reference_video_resource_id, data.reference_audio_resource_id) if value)
    if resource_ids:
        found = {row[0] for row in db.query(Resource.id).filter(Resource.owner_id == owner_id, Resource.deleted_at.is_(None), Resource.id.in_(resource_ids)).all()}
        if found != resource_ids: raise StoryboardValidationError("镜头引用素材不存在、已删除或不属于当前用户")


def create_shot(db: Session, owner_id: int, project_id: int, scene_id: int, body: ShotInput) -> Shot:
    project_service.owned_project(db, owner_id, project_id); _owned_scene(db, owner_id, project_id, scene_id); _validate_refs(db, owner_id, project_id, body)
    count = db.query(func.count(Shot.id)).filter(Shot.scene_id == scene_id).scalar() or 0
    item = Shot(owner_id=owner_id, scene_id=scene_id, shot_no=count+1, sort_order=count, **body.model_dump()); db.add(item); db.commit(); db.refresh(item); return item


def update_shot(db: Session, owner_id: int, project_id: int, shot_id: int, body: ShotPatchIn) -> Shot:
    item = _owned_shot(db, owner_id, project_id, shot_id)
    if item.lock_version != body.lock_version: raise project_service.ProjectConflictError("镜头已被其他页面更新")
    _validate_refs(db, owner_id, project_id, body)
    for key, value in body.model_dump(exclude={"lock_version"}).items(): setattr(item, key, value)
    item.lock_version += 1; db.commit(); db.refresh(item); return item


def delete_shot(db: Session, owner_id: int, project_id: int, shot_id: int) -> None:
    item = _owned_shot(db, owner_id, project_id, shot_id); scene_id = item.scene_id; db.delete(item); db.flush(); _renumber(db, scene_id); db.commit()


def copy_shot(db: Session, owner_id: int, project_id: int, shot_id: int) -> Shot:
    source = _owned_shot(db, owner_id, project_id, shot_id); data = {column.name: getattr(source, column.name) for column in Shot.__table__.columns if column.name not in {"id", "created_at", "updated_at", "shot_no", "sort_order", "lock_version"}}
    items = db.query(Shot).filter(Shot.scene_id == source.scene_id).order_by(Shot.sort_order).all()
    for item in items:
        if item.sort_order > source.sort_order: item.sort_order += 1
    data["status"] = "draft"; copied = Shot(**data, shot_no=len(items)+1, sort_order=source.sort_order+1, lock_version=1); db.add(copied); db.flush(); _renumber(db, source.scene_id); db.commit(); db.refresh(copied); return copied


def split_shot(db: Session, owner_id: int, project_id: int, shot_id: int, ratio: float) -> list[Shot]:
    source = _owned_shot(db, owner_id, project_id, shot_id); source.status = "draft"; first = round(source.duration * ratio, 2); second = round(source.duration - first, 2); source.duration = first; source.lock_version += 1
    copied = copy_shot(db, owner_id, project_id, shot_id); copied.duration = second; copied.visual_description = f"{copied.visual_description}（后半段）"; db.commit(); db.refresh(source); db.refresh(copied); return [source, copied]


def merge_shots(db: Session, owner_id: int, project_id: int, shot_ids: list[int]) -> Shot:
    items = [_owned_shot(db, owner_id, project_id, item_id) for item_id in dict.fromkeys(shot_ids)]
    if len(items) < 2 or len({item.scene_id for item in items}) != 1: raise StoryboardValidationError("只能合并同一场景中的多个镜头")
    items.sort(key=lambda item: item.sort_order); first = items[0]
    first.visual_description = "\n".join(filter(None, (item.visual_description for item in items)))
    first.action = "\n".join(filter(None, (item.action for item in items))); first.dialogue = "\n".join(filter(None, (item.dialogue for item in items)))
    first.duration = round(sum(item.duration for item in items), 2); first.character_ids = sorted({value for item in items for value in (item.character_ids or [])}); first.prop_ids = sorted({value for item in items for value in (item.prop_ids or [])}); first.status = "draft"; first.lock_version += 1
    for item in items[1:]: db.delete(item)
    db.flush(); _renumber(db, first.scene_id); db.commit(); db.refresh(first); return first


def reorder(db: Session, owner_id: int, project_id: int, scene_id: int, shot_ids: list[int]) -> list[Shot]:
    _owned_scene(db, owner_id, project_id, scene_id); items = db.query(Shot).filter(Shot.scene_id == scene_id, Shot.owner_id == owner_id).all()
    if {item.id for item in items} != set(shot_ids) or len(items) != len(shot_ids): raise StoryboardValidationError("镜头排序列表必须完整且不能重复")
    mapping = {item.id: item for item in items}
    for index, item_id in enumerate(shot_ids): mapping[item_id].sort_order = index; mapping[item_id].shot_no = -(index+1)
    db.flush(); _renumber(db, scene_id); db.commit(); return db.query(Shot).filter(Shot.scene_id == scene_id).order_by(Shot.sort_order).all()


def bulk_patch(db: Session, owner_id: int, project_id: int, body: ShotBulkPatchIn) -> list[Shot]:
    items = [_owned_shot(db, owner_id, project_id, item_id) for item_id in dict.fromkeys(body.shot_ids)]
    for item in items:
        if body.duration is not None: item.duration = body.duration
        if body.status is not None: item.status = body.status
        settings = dict(item.production_settings or {})
        if body.aspect_ratio is not None: settings["aspect_ratio"] = body.aspect_ratio
        if body.quality_tier is not None: settings["quality_tier"] = body.quality_tier
        item.production_settings = settings; item.lock_version += 1
    db.commit()
    for item in items: db.refresh(item)
    return items


def blockers(db: Session, shot: Shot) -> list[str]:
    result: list[str] = []
    if shot.character_ids:
        unconfirmed = db.query(func.count(Character.id)).filter(Character.id.in_(shot.character_ids), Character.status != "confirmed").scalar() or 0
        if unconfirmed: result.append(f"{unconfirmed} 个角色尚未确认")
    if shot.location_id and db.query(Location.id).filter(Location.id == shot.location_id, Location.status != "confirmed").first(): result.append("地点尚未确认")
    if not shot.visual_description: result.append("缺少画面描述")
    return result


def overview(db: Session, owner_id: int, project_id: int) -> tuple[ShortDramaProject, list[Episode], dict[int, list[Shot]]]:
    project = project_service.owned_project(db, owner_id, project_id)
    episodes = db.query(Episode).options(selectinload(Episode.scenes)).filter(Episode.owner_id == owner_id, Episode.project_id == project_id).order_by(Episode.sort_order).all()
    scene_ids = [scene.id for episode in episodes for scene in episode.scenes]
    shots = db.query(Shot).filter(Shot.owner_id == owner_id, Shot.scene_id.in_(scene_ids)).order_by(Shot.scene_id, Shot.sort_order).all() if scene_ids else []
    by_scene: dict[int, list[Shot]] = {}
    for item in shots: by_scene.setdefault(item.scene_id, []).append(item)
    return project, episodes, by_scene
