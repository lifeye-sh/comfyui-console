"""角色、地点、关系与道具设定候选及人工维护。"""
from __future__ import annotations

from datetime import UTC, datetime
from itertools import combinations
import re
from typing import Any, TypeVar

from sqlalchemy.orm import Session

from app.models import (
    AuditLog, Character, CharacterRelationship, CharacterVariant, Episode, Location, Prop,
    Resource, Scene, Shot, ShortDramaProject, StoryVersion, WorldCandidate,
)
from app.schemas.short_drama import CharacterInput, CharacterVariantInput, LocationInput, PropInput, RelationshipInput
from app.short_drama import project_service

T = TypeVar("T", Character, Location, Prop)


class WorldValidationError(ValueError): pass


def _now() -> datetime: return datetime.now(UTC).replace(tzinfo=None)


def _audit(db: Session, owner_id: int, action: str, project_id: int, detail: str = "") -> None:
    db.add(AuditLog(user_id=owner_id, action=action, target_type="short_drama_project", target_id=project_id, detail=detail or None))


def _validate_resources(db: Session, owner_id: int, ids: list[int], primary: int | None = None) -> None:
    wanted = set(ids + ([primary] if primary else []))
    if not wanted: return
    found = {row[0] for row in db.query(Resource.id).filter(Resource.owner_id == owner_id, Resource.deleted_at.is_(None), Resource.id.in_(wanted)).all()}
    if found != wanted: raise WorldValidationError("引用素材不存在、已删除或不属于当前用户")


def extract_candidate(db: Session, owner_id: int, project_id: int) -> WorldCandidate:
    project = project_service.owned_project(db, owner_id, project_id)
    version = db.query(StoryVersion).filter(StoryVersion.owner_id == owner_id, StoryVersion.project_id == project_id, StoryVersion.is_current.is_(True)).first()
    if not version: raise WorldValidationError("请先确认或保存一个剧本版本")
    scenes = db.query(Scene).join(Episode, Episode.id == Scene.episode_id).filter(Episode.project_id == project_id, Scene.owner_id == owner_id).order_by(Episode.sort_order, Scene.sort_order).all()
    characters: dict[str, dict[str, Any]] = {}; locations: dict[str, dict[str, Any]] = {}; props: dict[str, dict[str, Any]] = {}; pairs: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for scene in scenes:
        references = list(scene.source_references or [])
        speakers: list[str] = []
        for element in scene.elements or []:
            if element.get("type") == "dialogue" and str(element.get("speaker", "")).strip():
                name = str(element["speaker"]).strip()[:128]; speakers.append(name)
                item = characters.setdefault(name, {"name": name, "aliases": [], "identity": "", "age_appearance": "", "appearance": "", "personality": "", "relationships": {}, "negative_traits": [], "source_references": []})
                for ref in references:
                    if ref not in item["source_references"]: item["source_references"].append(ref)
            if element.get("type") in {"action", "narration"}:
                text_value = str(element.get("text", ""))
                explicit = re.findall(r"[【\[]道具[:：]([^】\]]+)[】\]]", text_value)
                common = [word for word in ("手机", "钥匙", "项链", "戒指", "照片", "信件", "药瓶", "手枪", "长剑", "箱子") if word in text_value]
                for name in dict.fromkeys(explicit + common):
                    name = name.strip()[:160]
                    if not name: continue
                    prop = props.setdefault(name, {"name": name, "description": "", "appearance": "", "appearance_scope": "", "owner_character_id": None, "continuity_note": "", "source_references": [], "reference_resource_ids": [], "resource_id": None, "status": "draft"})
                    for ref in references:
                        if ref not in prop["source_references"]: prop["source_references"].append(ref)
        for first, second in combinations(sorted(set(speakers)), 2):
            pairs.setdefault((first, second), []).extend(ref for ref in references if ref not in pairs.get((first, second), []))
        if scene.location_name.strip():
            name = scene.location_name.strip()[:160]
            item = locations.setdefault(name, {"name": name, "description": "", "spatial_layout": "", "time_weather": scene.time_of_day, "lighting": "", "color_palette": [], "fixed_objects": [], "source_references": []})
            for ref in references:
                if ref not in item["source_references"]: item["source_references"].append(ref)
    relationships = [{"source_name": a, "target_name": b, "relationship_type": "同场角色", "description": "在同一场景出现", "source_references": refs} for (a, b), refs in pairs.items()]
    existing_characters = {item.name for item in db.query(Character).filter(Character.owner_id == owner_id, Character.project_id == project_id).all()}
    existing_locations = {item.name for item in db.query(Location).filter(Location.owner_id == owner_id, Location.project_id == project_id).all()}
    conflicts = ([{"entity_type": "character", "name": name, "resolution": "skip_existing"} for name in characters if name in existing_characters] + [{"entity_type": "location", "name": name, "resolution": "skip_existing"} for name in locations if name in existing_locations])
    existing_props = {item.name for item in db.query(Prop).filter(Prop.owner_id == owner_id, Prop.project_id == project_id).all()}
    conflicts.extend({"entity_type": "prop", "name": name, "resolution": "skip_existing"} for name in props if name in existing_props)
    candidate = WorldCandidate(owner_id=owner_id, project_id=project_id, story_version_id=version.id, status="pending", payload={"characters": list(characters.values()), "locations": list(locations.values()), "relationships": relationships, "props": list(props.values())}, conflicts=conflicts)
    db.add(candidate); _audit(db, owner_id, "short_drama.world.preview", project_id, f"version={version.id}"); db.commit(); db.refresh(candidate)
    return candidate


def owned_candidate(db: Session, owner_id: int, project_id: int, candidate_id: int) -> WorldCandidate:
    item = db.query(WorldCandidate).filter(WorldCandidate.id == candidate_id, WorldCandidate.owner_id == owner_id, WorldCandidate.project_id == project_id).first()
    if not item: raise project_service.ProjectNotFoundError("设定候选不存在")
    return item


def confirm_candidate(db: Session, owner_id: int, project_id: int, candidate_id: int, skip_existing: bool) -> WorldCandidate:
    project_service.owned_project(db, owner_id, project_id); candidate = owned_candidate(db, owner_id, project_id, candidate_id)
    if candidate.status == "confirmed": return candidate
    if candidate.status != "pending": raise WorldValidationError("该候选不能确认")
    payload = candidate.payload or {}; character_map = {item.name: item for item in db.query(Character).filter(Character.owner_id == owner_id, Character.project_id == project_id).all()}
    location_map = {item.name: item for item in db.query(Location).filter(Location.owner_id == owner_id, Location.project_id == project_id).all()}
    prop_map = {item.name: item for item in db.query(Prop).filter(Prop.owner_id == owner_id, Prop.project_id == project_id).all()}
    for data in payload.get("characters", []):
        if data["name"] in character_map:
            if not skip_existing: raise WorldValidationError(f"角色“{data['name']}”已存在；为保护人工设定不能覆盖")
            continue
        item = Character(owner_id=owner_id, project_id=project_id, status="draft", **data); db.add(item); db.flush(); character_map[item.name] = item
    for data in payload.get("locations", []):
        if data["name"] in location_map:
            if not skip_existing: raise WorldValidationError(f"地点“{data['name']}”已存在；为保护人工设定不能覆盖")
            continue
        item = Location(owner_id=owner_id, project_id=project_id, status="draft", **data); db.add(item); db.flush(); location_map[item.name] = item
    for data in payload.get("props", []):
        if data["name"] in prop_map:
            if not skip_existing: raise WorldValidationError(f"道具“{data['name']}”已存在；为保护人工设定不能覆盖")
            continue
        item = Prop(owner_id=owner_id, project_id=project_id, **data); db.add(item); db.flush(); prop_map[item.name] = item
    for data in payload.get("relationships", []):
        source = character_map.get(data["source_name"]); target = character_map.get(data["target_name"])
        if not source or not target: continue
        exists = db.query(CharacterRelationship.id).filter(CharacterRelationship.project_id == project_id, CharacterRelationship.source_character_id == source.id, CharacterRelationship.target_character_id == target.id).first()
        if not exists: db.add(CharacterRelationship(owner_id=owner_id, project_id=project_id, source_character_id=source.id, target_character_id=target.id, relationship_type=data["relationship_type"], description=data["description"], source_references=data["source_references"], status="draft"))
    scenes = db.query(Scene).join(Episode, Episode.id == Scene.episode_id).filter(Episode.project_id == project_id, Scene.owner_id == owner_id).all()
    for scene in scenes:
        names = {str(e.get("speaker", "")).strip() for e in scene.elements or [] if e.get("type") == "dialogue"}
        scene.character_ids = sorted({character_map[name].id for name in names if name in character_map})
        scene.location_id = location_map.get(scene.location_name).id if scene.location_name in location_map else None
    candidate.status = "confirmed"; candidate.confirmed_at = _now(); _audit(db, owner_id, "short_drama.world.confirm", project_id, f"candidate={candidate.id}"); db.commit(); db.refresh(candidate)
    return candidate


def overview(db: Session, owner_id: int, project_id: int) -> tuple[list[Character], list[Location], list[Prop], list[CharacterRelationship]]:
    project_service.owned_project(db, owner_id, project_id)
    return (
        db.query(Character).filter(Character.owner_id == owner_id, Character.project_id == project_id).order_by(Character.id).all(),
        db.query(Location).filter(Location.owner_id == owner_id, Location.project_id == project_id).order_by(Location.id).all(),
        db.query(Prop).filter(Prop.owner_id == owner_id, Prop.project_id == project_id).order_by(Prop.id).all(),
        db.query(CharacterRelationship).filter(CharacterRelationship.owner_id == owner_id, CharacterRelationship.project_id == project_id).order_by(CharacterRelationship.id).all(),
    )


def _owned(db: Session, model: type[T], owner_id: int, project_id: int, item_id: int) -> T:
    item = db.query(model).filter(model.id == item_id, model.owner_id == owner_id, model.project_id == project_id).first()
    if not item: raise project_service.ProjectNotFoundError("设定不存在")
    return item


def save_character(db: Session, owner_id: int, project_id: int, body: CharacterInput, item_id: int | None = None) -> Character:
    project_service.owned_project(db, owner_id, project_id); _validate_resources(db, owner_id, body.reference_resource_ids, body.primary_resource_id)
    item = _owned(db, Character, owner_id, project_id, item_id) if item_id else Character(owner_id=owner_id, project_id=project_id)
    for key, value in body.model_dump().items(): setattr(item, key, value)
    if not item_id: db.add(item)
    db.commit(); db.refresh(item); return item


def save_character_variant(db: Session, owner_id: int, project_id: int, character_id: int, body: CharacterVariantInput, item_id: int | None = None) -> CharacterVariant:
    project_service.owned_project(db, owner_id, project_id); _owned(db, Character, owner_id, project_id, character_id)
    _validate_resources(db, owner_id, body.reference_resource_ids, body.primary_resource_id)
    if item_id:
        item = db.query(CharacterVariant).filter(CharacterVariant.id == item_id, CharacterVariant.owner_id == owner_id, CharacterVariant.character_id == character_id).first()
        if not item: raise project_service.ProjectNotFoundError("角色造型不存在")
    else:
        item = CharacterVariant(owner_id=owner_id, character_id=character_id)
    for key, value in body.model_dump().items(): setattr(item, key, value)
    if not item_id: db.add(item)
    db.commit(); db.refresh(item); return item


def delete_character_variant(db: Session, owner_id: int, project_id: int, character_id: int, item_id: int) -> None:
    project_service.owned_project(db, owner_id, project_id); _owned(db, Character, owner_id, project_id, character_id)
    item = db.query(CharacterVariant).filter(CharacterVariant.id == item_id, CharacterVariant.owner_id == owner_id, CharacterVariant.character_id == character_id).first()
    if not item: raise project_service.ProjectNotFoundError("角色造型不存在")
    db.delete(item); db.commit()


def save_location(db: Session, owner_id: int, project_id: int, body: LocationInput, item_id: int | None = None) -> Location:
    project_service.owned_project(db, owner_id, project_id); _validate_resources(db, owner_id, body.reference_resource_ids, body.primary_resource_id)
    item = _owned(db, Location, owner_id, project_id, item_id) if item_id else Location(owner_id=owner_id, project_id=project_id)
    for key, value in body.model_dump().items(): setattr(item, key, value)
    if not item_id: db.add(item)
    db.commit(); db.refresh(item); return item


def save_prop(db: Session, owner_id: int, project_id: int, body: PropInput, item_id: int | None = None) -> Prop:
    project_service.owned_project(db, owner_id, project_id); _validate_resources(db, owner_id, body.reference_resource_ids, body.resource_id)
    if body.owner_character_id and not db.query(Character.id).filter(Character.id == body.owner_character_id, Character.owner_id == owner_id, Character.project_id == project_id).first(): raise WorldValidationError("道具归属角色不存在")
    item = _owned(db, Prop, owner_id, project_id, item_id) if item_id else Prop(owner_id=owner_id, project_id=project_id)
    for key, value in body.model_dump().items(): setattr(item, key, value)
    if not item_id: db.add(item)
    db.commit(); db.refresh(item); return item


def save_relationship(db: Session, owner_id: int, project_id: int, body: RelationshipInput, item_id: int | None = None) -> CharacterRelationship:
    project_service.owned_project(db, owner_id, project_id)
    ids = {row[0] for row in db.query(Character.id).filter(Character.owner_id == owner_id, Character.project_id == project_id, Character.id.in_([body.source_character_id, body.target_character_id])).all()}
    if ids != {body.source_character_id, body.target_character_id} or body.source_character_id == body.target_character_id: raise WorldValidationError("关系角色不存在或不能指向自身")
    item = _owned(db, CharacterRelationship, owner_id, project_id, item_id) if item_id else CharacterRelationship(owner_id=owner_id, project_id=project_id)
    for key, value in body.model_dump().items(): setattr(item, key, value)
    if not item_id: db.add(item)
    db.commit(); db.refresh(item); return item


def delete_item(db: Session, model: type[T], owner_id: int, project_id: int, item_id: int) -> None:
    item = _owned(db, model, owner_id, project_id, item_id)
    if model is Character:
        used = db.query(Scene.id).join(Episode, Episode.id == Scene.episode_id).filter(Episode.project_id == project_id).all()
        if any(item_id in (db.get(Scene, row[0]).character_ids or []) for row in used): raise WorldValidationError("角色正在被剧本场景引用，不能删除")
    if model is Location and db.query(Scene.id).filter(Scene.location_id == item_id).first(): raise WorldValidationError("地点正在被剧本场景引用，不能删除")
    db.delete(item); db.commit()


def resource_usages(db: Session, owner_id: int, resource_id: int) -> list[dict[str, Any]]:
    resource = db.query(Resource).filter(Resource.id == resource_id, Resource.owner_id == owner_id).first()
    if not resource: raise project_service.ProjectNotFoundError("素材不存在")
    result: list[dict[str, Any]] = []
    for model, label, primary_field in ((Character, "character", "primary_resource_id"), (Location, "location", "primary_resource_id"), (Prop, "prop", "resource_id")):
        for item in db.query(model).filter(model.owner_id == owner_id).all():
            if getattr(item, primary_field) == resource_id or resource_id in (item.reference_resource_ids or []): result.append({"entity_type": label, "entity_id": item.id, "project_id": item.project_id, "name": item.name})
    for item in db.query(CharacterVariant).filter(CharacterVariant.owner_id == owner_id).all():
        if item.primary_resource_id == resource_id or resource_id in (item.reference_resource_ids or []): result.append({"entity_type": "character_variant", "entity_id": item.id, "name": item.name})
    for item in db.query(Shot).filter(Shot.owner_id == owner_id).all():
        bound = resource_id in (item.reference_resource_ids or []) or resource_id in (
            item.first_frame_resource_id, item.last_frame_resource_id, item.pose_resource_id,
            item.reference_video_resource_id, item.reference_audio_resource_id,
        )
        if bound:
            scene = db.get(Scene, item.scene_id); episode = db.get(Episode, scene.episode_id) if scene else None
            result.append({"entity_type": "shot", "entity_id": item.id, "project_id": episode.project_id if episode else None, "name": f"镜头 {item.shot_no}"})
    return result
