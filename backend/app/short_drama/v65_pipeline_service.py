"""short-drama-director V6.5 asset-first pipeline gates.

The skill is the workflow authority. This service derives gate state from the
existing domain records and stores only user confirmations in project.settings,
so imported and generated data share the same pipeline.
"""
from __future__ import annotations

from typing import Any
from sqlalchemy.orm import Session

from app.models import Character, Episode, Location, Prop, Scene, ShortDramaProject, Shot
from app.short_drama import project_service
from app.short_drama.skill_contracts import SKILL_MANIFEST, SKILL_VERSION


def _episode(db: Session, owner_id: int, project_id: int, episode_id: int) -> Episode:
    project_service.owned_project(db, owner_id, project_id)
    item = db.query(Episode).filter_by(id=episode_id, project_id=project_id, owner_id=owner_id).first()
    if not item:
        raise project_service.ProjectNotFoundError("分集不存在")
    return item


def _state(project: ShortDramaProject, episode_id: int) -> dict[str, Any]:
    settings = dict(project.settings or {})
    pipeline = dict(settings.get("v65_pipeline") or {})
    return dict(pipeline.get(str(episode_id)) or {})


def _save_state(db: Session, project: ShortDramaProject, episode_id: int, state: dict[str, Any]) -> None:
    settings = dict(project.settings or {})
    pipeline = dict(settings.get("v65_pipeline") or {})
    pipeline[str(episode_id)] = state
    settings["v65_pipeline"] = pipeline
    settings["director_skill"] = {"id": "short-drama-director", "version": SKILL_VERSION, "schema_version": "2.0"}
    project.settings = settings
    db.commit()


def snapshot(db: Session, owner_id: int, project_id: int, episode_id: int) -> dict[str, Any]:
    episode = _episode(db, owner_id, project_id, episode_id)
    project = project_service.owned_project(db, owner_id, project_id)
    scenes = db.query(Scene).filter_by(episode_id=episode_id, owner_id=owner_id).order_by(Scene.sort_order).all()
    shots = (db.query(Shot).join(Scene, Shot.scene_id == Scene.id)
             .filter(Scene.episode_id == episode_id, Shot.owner_id == owner_id)
             .order_by(Scene.sort_order, Shot.sort_order).all())
    chars = db.query(Character).filter_by(project_id=project_id, owner_id=owner_id).order_by(Character.id).all()
    locs = db.query(Location).filter_by(project_id=project_id, owner_id=owner_id).order_by(Location.id).all()
    props = db.query(Prop).filter_by(project_id=project_id, owner_id=owner_id).order_by(Prop.id).all()
    state = _state(project, episode_id)

    requirements: list[dict[str, Any]] = []
    for idx, item in enumerate(chars, 1):
        requirements.append({"stable_key": f"CHR-{idx:03d}", "entity_type": "character", "entity_id": item.id,
            "name": item.name, "grade": "A" if idx <= 2 else "B", "required": True,
            "ready": bool(item.primary_resource_id), "resource_id": item.primary_resource_id,
            "reason": "出镜角色必须先锁定身份图"})
    used_locations = {s.location_id for s in scenes if s.location_id}
    for idx, item in enumerate(locs, 1):
        required = item.id in used_locations
        requirements.append({"stable_key": f"SCN-{idx:03d}", "entity_type": "location", "entity_id": item.id,
            "name": item.name, "grade": "A" if required else "C", "required": required,
            "ready": bool(item.primary_resource_id), "resource_id": item.primary_resource_id,
            "reason": "进入分镜的场景必须先锁定场景图" if required else "未在本集使用"})
    used_props = {pid for shot in shots for pid in (shot.prop_ids or [])}
    for idx, item in enumerate(props, 1):
        required = item.id in used_props
        requirements.append({"stable_key": f"PRP-{idx:03d}", "entity_type": "prop", "entity_id": item.id,
            "name": item.name, "grade": "B" if required else "C", "required": required,
            "ready": bool(item.resource_id), "resource_id": item.resource_id,
            "reason": "本集连续性道具必须先锁定参考图" if required else "未在本集使用"})

    pending_assets = [x for x in requirements if x["required"] and not x["ready"]]
    asset_ready = bool(requirements) and not pending_assets
    asset_locked = asset_ready and bool(state.get("asset_atlas_locked"))
    spatial_issues = []
    for idx, scene in enumerate(scenes, 1):
        loc = next((x for x in locs if x.id == scene.location_id), None)
        if not loc or not str(loc.spatial_layout or "").strip():
            spatial_issues.append({"type": "location_layout", "scene_id": scene.id, "label": scene.heading or f"场景 {idx}", "message": "缺少 3D 空间快照、动作轴线与 CAM1～CAM4 机位"})
    for shot in shots:
        if not str(shot.timeline_storyboard or "").strip():
            spatial_issues.append({"type": "timeline", "shot_id": shot.id, "label": f"镜头 {shot.shot_no}", "message": "缺少时间轴分镜"})
    spatial_ready = asset_locked and bool(shots) and not spatial_issues
    spatial_locked = spatial_ready and bool(state.get("spatial_storyboard_locked"))
    prompt_ready = bool(shots) and all(str(x.video_prompt or "").strip() for x in shots)
    quality_issues = []
    if not asset_locked: quality_issues.append({"level": "P0", "message": "资产图册尚未锁定"})
    if not spatial_locked: quality_issues.append({"level": "P0", "message": "空间走位与分镜尚未确认"})
    for shot in shots:
        meta = shot.production_settings or {}
        if not meta.get("speech_rate_check"):
            quality_issues.append({"level": "P1", "shot_id": shot.id, "message": "缺少语速自检"})
        if not str(shot.video_prompt or "").strip():
            quality_issues.append({"level": "P1", "shot_id": shot.id, "message": "缺少模型适配视频提示词"})

    stages = [
        {"id": "P0", "name": "项目锁定", "status": "passed" if project.brief and project.brief.aspect_ratio and project.brief.visual_style else "blocked"},
        {"id": "P1", "name": "剧本与剧组产出册", "status": "passed" if episode.status == "manifest_confirmed" and shots else "blocked"},
        {"id": "P2", "name": "数字资产包与资产图册", "status": "passed" if asset_locked else ("ready" if asset_ready else "blocked")},
        {"id": "P3", "name": "空间走位与分镜", "status": "passed" if spatial_locked else ("ready" if spatial_ready else "blocked")},
        {"id": "P4", "name": "视频提示词与制作", "status": "passed" if prompt_ready else ("ready" if spatial_locked else "blocked")},
        {"id": "P5", "name": "P0/P1/P2 质检", "status": "passed" if prompt_ready and not quality_issues else "blocked"},
    ]
    return {"skill": SKILL_MANIFEST, "project_id": project_id, "episode_id": episode_id, "stages": stages,
        "requirements": requirements, "pending_assets": pending_assets, "asset_atlas_locked": asset_locked,
        "spatial_issues": spatial_issues, "spatial_storyboard_locked": spatial_locked,
        "prompt_ready": prompt_ready, "quality_issues": quality_issues,
        "counts": {"scenes": len(scenes), "shots": len(shots), "characters": len(chars), "locations": len(locs), "props": len(props)}}


def confirm_asset_atlas(db: Session, owner_id: int, project_id: int, episode_id: int) -> dict[str, Any]:
    current = snapshot(db, owner_id, project_id, episode_id)
    if current["pending_assets"]:
        names = "、".join(x["name"] for x in current["pending_assets"])
        raise project_service.ProjectConflictError(f"无资产图不分镜：请先锁定 {names}")
    project = project_service.owned_project(db, owner_id, project_id)
    state = _state(project, episode_id)
    state["asset_atlas_locked"] = True
    state["spatial_storyboard_locked"] = False
    project.stage = "spatial_storyboard"
    _save_state(db, project, episode_id, state)
    return snapshot(db, owner_id, project_id, episode_id)


def confirm_spatial_storyboard(db: Session, owner_id: int, project_id: int, episode_id: int) -> dict[str, Any]:
    current = snapshot(db, owner_id, project_id, episode_id)
    if not current["asset_atlas_locked"]:
        raise project_service.ProjectConflictError("请先锁定资产图册")
    if current["spatial_issues"]:
        raise project_service.ProjectConflictError("空间分镜未通过：" + "；".join(x["message"] for x in current["spatial_issues"][:3]))
    project = project_service.owned_project(db, owner_id, project_id)
    state = _state(project, episode_id)
    state["spatial_storyboard_locked"] = True
    project.stage = "video_prompts"
    _save_state(db, project, episode_id, state)
    return snapshot(db, owner_id, project_id, episode_id)


def require_video_prompt_gate(db: Session, owner_id: int, project_id: int, episode_id: int) -> dict[str, Any]:
    current = snapshot(db, owner_id, project_id, episode_id)
    if not current["asset_atlas_locked"]:
        raise project_service.ProjectConflictError("V6.5 门禁：资产图册未锁定")
    if not current["spatial_storyboard_locked"]:
        raise project_service.ProjectConflictError("V6.5 门禁：空间走位与分镜未确认")
    return current
