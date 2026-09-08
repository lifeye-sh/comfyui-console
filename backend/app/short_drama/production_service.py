"""Bridge storyboard shots to the existing task engine and reconcile outputs as Takes."""
from __future__ import annotations

import math
from app.short_drama.dialogue import total_duration

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.comfy.prompt_builder import build_prompt
from app.models import (
    AuditLog, Batch, Character, Episode, GenerationType, Location, ProjectBrief, Resource,
    Scene, ShortDramaProject, Shot, ShotTaskLink, Take, Task, TaskResource, Workflow, WorkflowVersion,
)
from app.schemas.short_drama import ShotProductionCompileIn, ShotProductionCreateIn
from app.services.video_rules import duration_errors
from app.short_drama import project_service, storyboard_service


class ProductionValidationError(ValueError): pass


try:  # Python 3.11+
    from datetime import UTC  # type: ignore[attr-defined]
except ImportError:  # Python 3.10 fallback
    from datetime import timezone as _tz
    UTC = _tz.utc  # type: ignore[assignment]


def _now() -> datetime: return datetime.now(UTC).replace(tzinfo=None)


def _audit(db: Session, owner_id: int, action: str, project_id: int, detail: str = "") -> None:
    db.add(AuditLog(user_id=owner_id, action=action, target_type="short_drama_project", target_id=project_id, detail=detail or None))


def _workflow(db: Session, owner_id: int, generation_type: GenerationType, version_id: int | None) -> tuple[Workflow, WorkflowVersion]:
    if version_id:
        version = db.get(WorkflowVersion, version_id); workflow = db.get(Workflow, version.workflow_id) if version else None
    else:
        workflow = db.get(Workflow, generation_type.default_workflow_id) if generation_type.default_workflow_id else None
        version = db.get(WorkflowVersion, workflow.current_version_id) if workflow and workflow.current_version_id else None
    if not workflow or not version or workflow.generation_type_id != generation_type.id or workflow.status != "active":
        raise ProductionValidationError("生成类型没有可用的匹配工作流")
    if workflow.owner_id not in (None, owner_id): raise ProductionValidationError("工作流不属于当前用户")
    return workflow, version


def _shot_context(db: Session, owner_id: int, project_id: int, shot_id: int) -> tuple[Shot, Scene, Episode, ShortDramaProject]:
    shot = storyboard_service._owned_shot(db, owner_id, project_id, shot_id); scene = db.get(Scene, shot.scene_id); episode = db.get(Episode, scene.episode_id) if scene else None
    project = project_service.owned_project(db, owner_id, project_id)
    if not scene or not episode: raise project_service.ProjectNotFoundError("镜头场景不存在")
    return shot, scene, episode, project


def _prompt(db: Session, shot: Shot, scene: Scene, project: ShortDramaProject) -> str:
    character_parts: list[str] = []
    if shot.character_ids:
        for item in db.query(Character).filter(Character.id.in_(shot.character_ids), Character.project_id == project.id).all():
            character_parts.append(f"{item.name}（{item.identity}；{item.appearance}；{item.personality}）")
    location = db.get(Location, shot.location_id) if shot.location_id else None
    parts = [
        shot.visual_description, f"动作：{shot.action}" if shot.action else "", f"表情：{shot.expression}" if shot.expression else "",
        f"对白：{shot.dialogue}" if shot.dialogue else "", f"角色：{'；'.join(character_parts)}" if character_parts else "",
        f"地点：{location.name}；{location.description}；{location.lighting}" if location else f"场景：{scene.location_name}",
        f"镜头：{shot.shot_size}，{shot.camera_angle}，{shot.camera_movement}，{shot.composition}",
        f"情绪：{shot.mood}" if shot.mood else "", f"项目视觉风格：{project.brief.visual_style}" if project.brief and project.brief.visual_style else "",
    ]
    settings = shot.production_settings or {}
    bundle = settings.get("manifest_prompt") or {}
    if bundle:
        from app.short_drama.phase1_service import _prompt_bundle
        effective = _prompt_bundle({"prompt": bundle})["effective"]
        parts = [value for key, value in effective.items() if key != "negative_constraints"]
        # Dialogue is preserved verbatim even when the visual description is overridden.
        parts.extend(f"{line['speaker']}：{line['text']}" for line in settings.get("dialogue_lines", []))
        if character_parts and not effective.get("character_consistency"):
            parts.append("角色：" + "；".join(character_parts))
        for key in ("narration", "inner_monologue"):
            value = str(settings.get(key) or "")
            if value and not any(value in str(part) for part in parts):
                parts.append(("旁白：" if key == "narration" else "内心独白：") + value)
        if effective.get("negative_constraints"):
            parts.append("负面约束：" + effective["negative_constraints"])
    keyframe_plan = settings.get("keyframe_plan") or {}
    strategy_label = {"first": "首帧", "last": "尾帧", "first_last": "首尾帧", "multi": "多关键帧"}.get(
        str(keyframe_plan.get("strategy") or ""), str(keyframe_plan.get("strategy") or ""))
    if strategy_label:
        parts.append(f"关键帧策略：{strategy_label}")
    if keyframe_plan.get("first_frame_prompt"):
        parts.append(f"首帧画面：{keyframe_plan['first_frame_prompt']}")
    if keyframe_plan.get("last_frame_prompt"):
        parts.append(f"尾帧画面：{keyframe_plan['last_frame_prompt']}")
    for kf in keyframe_plan.get("keyframes") or []:
        if isinstance(kf, dict) and kf.get("prompt"):
            parts.append(f"{kf.get('label') or '关键帧'}：{kf['prompt']}")
    reaction = float(settings.get("reaction_pause") or 0)
    if reaction > 0:
        parts.append(f"对白结束后保留约 {reaction:g} 秒人物反应停顿")
    return "\n".join(value.strip() for value in parts if value and value.strip())


def _resources(db: Session, shot: Shot, project_id: int, owner_id: int) -> dict[str, list[int]]:
    candidates: list[int] = [value for value in (
        shot.first_frame_resource_id, shot.last_frame_resource_id, shot.pose_resource_id,
        shot.reference_video_resource_id, shot.reference_audio_resource_id,
    ) if value]
    candidates.extend(shot.reference_resource_ids or [])
    if shot.character_ids:
        for item in db.query(Character).filter(Character.id.in_(shot.character_ids), Character.project_id == project_id).all():
            if item.primary_resource_id: candidates.append(item.primary_resource_id)
            candidates.extend(item.reference_resource_ids or [])
    if shot.location_id:
        location = db.get(Location, shot.location_id)
        if location and location.project_id == project_id:
            if location.primary_resource_id: candidates.append(location.primary_resource_id)
            candidates.extend(location.reference_resource_ids or [])
    resources = db.query(Resource).filter(
        Resource.id.in_(set(candidates)), Resource.owner_id == owner_id, Resource.deleted_at.is_(None)
    ).all() if candidates else []
    by_id = {item.id: item for item in resources}
    grouped: dict[str, list[int]] = {"image": [], "video": [], "audio": []}
    for resource_id in dict.fromkeys(candidates):
        resource = by_id.get(resource_id)
        if resource and resource.media_type in grouped:
            grouped[resource.media_type].append(resource.id)
    return grouped


def _mapping_exists(api_json: dict[str, Any], spec: dict[str, Any]) -> bool:
    if not isinstance(spec, dict):
        return False
    # size 类型：复合参数（宽×高），映射信息在 targets.width / targets.height
    if spec.get("type") == "size":
        targets = spec.get("targets")
        if not isinstance(targets, dict):
            return False
        w = targets.get("width")
        h = targets.get("height")
        if not isinstance(w, dict) or not isinstance(h, dict):
            return False
        return (
            _mapping_exists(api_json, {**w, "type": "int", "key": "width"})
            and _mapping_exists(api_json, {**h, "type": "int", "key": "height"})
        )
    node = api_json.get(str(spec.get("node") or ""))
    if not isinstance(node, dict): return False
    parts = [part for part in str(spec.get("path") or "").split(".") if part]
    target: Any = node
    for part in parts[:-1]:
        if not isinstance(target, dict) or not isinstance(target.get(part), dict): return False
        target = target[part]
    if parts and isinstance(target, dict) and parts[-1] in target: return True
    inputs = node.get("inputs")
    if not isinstance(inputs, dict): return False
    kind = str(spec.get("type"))
    param_key = str(spec.get("key") or "")
    # 多媒体类型：按 image/video/audio 相关字段名模糊匹配
    if kind in {"image", "video", "audio"}:
        return any(k in inputs for k in (kind, f"input_{kind}", f"{kind}_path", "filename")) or any(kind in field.lower() for field in inputs)
    # 其他类型（select/int/float/text 等）：path 最后一段命中 inputs 即通过
    leaf = parts[-1] if parts else param_key
    if leaf and leaf in inputs:
        return True
    # 兜底：inputs 字段名与参数 key 精确归一化匹配（忽略大小写、下划线/连字符/空格）
    if param_key:
        norm_key = param_key.lower().replace("_", "").replace("-", "").replace(" ", "")
        if norm_key:
            for field in inputs:
                if str(field).lower().replace("_", "").replace("-", "").replace(" ", "") == norm_key:
                    return True
    return False


def _compile_one(db: Session, owner_id: int, project_id: int, shot_id: int, generation_type_id: int, workflow_version_id: int | None, overrides: dict[str, Any]) -> dict[str, Any]:
    shot, scene, _, project = _shot_context(db, owner_id, project_id, shot_id)
    generation_type = db.get(GenerationType, generation_type_id)
    if not generation_type or not generation_type.enabled: raise ProductionValidationError("生成类型不存在或已停用")
    workflow, version = _workflow(db, owner_id, generation_type, workflow_version_id)
    prompt = _prompt(db, shot, scene, project); resources = _resources(db, shot, project_id, owner_id); params: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []; warnings: list[dict[str, Any]] = []
    brief = project.brief; image_cursor = 0
    for spec in version.param_schema or []:
        key = str(spec.get("key") or "").strip()
        if not key: continue
        value = deepcopy(spec.get("default")); kind = spec.get("type"); lowered = key.lower()
        if kind in {"text", "textarea"} and lowered in {"prompt", "positive_prompt", "text", "description"}: value = prompt
        elif lowered in {"duration", "video_duration", "seconds"}:
            reaction = float((shot.production_settings or {}).get("reaction_pause") or 0)
            value = max(1, math.ceil(total_duration(shot.duration, shot.production_settings or {})))
        elif lowered in {"aspect_ratio", "ratio"} and brief: value = brief.aspect_ratio
        elif lowered in {"quality", "quality_tier"} and brief: value = brief.quality_tier
        elif kind == "image":
            preferred = shot.last_frame_resource_id if "last" in lowered or "end" in lowered else shot.pose_resource_id if "pose" in lowered else shot.first_frame_resource_id
            if preferred not in resources["image"]: preferred = None
            value = preferred or (resources["image"][image_cursor] if image_cursor < len(resources["image"]) else None); image_cursor += bool(value)
        elif kind == "video": value = shot.reference_video_resource_id if shot.reference_video_resource_id in resources["video"] else (resources["video"][0] if resources["video"] else None)
        elif kind == "audio": value = shot.reference_audio_resource_id if shot.reference_audio_resource_id in resources["audio"] else (resources["audio"][0] if resources["audio"] else None)
        params[key] = value
    params.update(overrides)
    for message in duration_errors(generation_type.media_type, params):
        warnings.append({"path": "duration", "code": "video_duration_advice", "message": message,
                         "actionable": True, "action": "set_duration", "action_label": "调整为15秒"})
    schema_keys = {str(item.get("key")) for item in version.param_schema or []}
    for key in overrides:
        if key not in schema_keys: warnings.append({"path": key, "code": "unknown_override", "message": "覆盖参数不在工作流映射中"})
    for spec in version.param_schema or []:
        key = str(spec.get("key") or "")
        if spec.get("required") and params.get(key) in (None, "", []): errors.append({"path": key, "code": "required", "message": f"缺少必填参数：{spec.get('label') or key}"})
        if not _mapping_exists(version.api_json or {}, spec):
            errors.append({"path": key, "code": "mapping_missing", "message": f"参数“{spec.get('label') or key}”没有有效的工作流节点映射"})
        if spec.get("type") in {"image", "video", "audio"} and params.get(key) not in (None, ""):
            try: resource_id = int(params[key])
            except (TypeError, ValueError): resource_id = 0
            resource = db.query(Resource).filter(
                Resource.id == resource_id, Resource.owner_id == owner_id, Resource.deleted_at.is_(None)
            ).first()
            if not resource or resource.media_type != spec.get("type"):
                errors.append({"path": key, "code": "invalid_resource", "message": f"参数“{spec.get('label') or key}”引用的素材不存在、无权访问或类型不匹配"})
            else: params[key] = resource_id
    try: build_prompt(version.api_json, version.param_schema or [], params)
    except Exception as exc: errors.append({"path": "workflow", "code": "mapping_failed", "message": str(exc)})
    input_ids = sorted({int(params[spec.get("key")]) for spec in version.param_schema or [] if spec.get("type") in {"image", "video", "audio"} and isinstance(params.get(spec.get("key")), int)})
    return {"shot_id": shot.id, "generation_type_id": generation_type.id, "generation_type_name": generation_type.name, "media_type": generation_type.media_type, "workflow_version_id": version.id, "workflow_name": workflow.name, "params": params, "prompt": prompt, "input_resource_ids": input_ids, "validation_errors": errors, "validation_warnings": warnings}


def compile_tasks(db: Session, owner_id: int, project_id: int, body: ShotProductionCompileIn) -> list[dict[str, Any]]:
    project_service.owned_project(db, owner_id, project_id)
    return [
        _compile_one(
            db, owner_id, project_id, shot_id, body.generation_type_id, body.workflow_version_id,
            {**body.parameter_overrides, **body.shot_parameter_overrides.get(shot_id, {})},
        )
        for shot_id in dict.fromkeys(body.shot_ids)
    ]


def create_tasks(db: Session, owner_id: int, project_id: int, body: ShotProductionCreateIn) -> tuple[Batch | None, list[Task], list[Task], list[ShotTaskLink]]:
    compiled = compile_tasks(db, owner_id, project_id, body)
    errors = [issue for item in compiled for issue in item["validation_errors"]]
    if errors: raise ProductionValidationError("工作流参数映射校验失败：" + "；".join(issue["message"] for issue in errors))
    existing_tasks: list[Task] = []; pending: list[dict[str, Any]] = []
    for item in compiled:
        key = f"shot:{item['shot_id']}:{body.idempotency_key}"
        existing = db.query(ShotTaskLink).filter(ShotTaskLink.owner_id == owner_id, ShotTaskLink.idempotency_key == key).first()
        if existing:
            task = db.get(Task, existing.task_id)
            if task: existing_tasks.append(task)
        else: pending.append({**item, "idempotency_key": key})
    batch: Batch | None = None; created: list[Task] = []; links: list[ShotTaskLink] = []
    if pending:
        batch = Batch(user_id=owner_id, name=f"短剧项目 #{project_id} 镜头生产", generation_type_id=body.generation_type_id, workflow_version_id=pending[0]["workflow_version_id"], global_params={}, source="short_drama", submitted_at=_now() if body.submit else None)
        db.add(batch); db.flush()
        generation_type = db.get(GenerationType, body.generation_type_id)
        for index, item in enumerate(pending):
            task = Task(batch_id=batch.id, row_no=index, user_id=owner_id, generation_type_id=body.generation_type_id, workflow_version_id=item["workflow_version_id"], config_version_id=generation_type.published_config_version_id if generation_type else None, params=item["params"], status="PENDING" if body.submit else "DRAFT")
            db.add(task); db.flush(); created.append(task)
            link = ShotTaskLink(owner_id=owner_id, shot_id=item["shot_id"], task_id=task.id, purpose="generate", status="linked", idempotency_key=item["idempotency_key"])
            db.add(link); links.append(link)
        project = project_service.owned_project(db, owner_id, project_id)
        if body.save_as_project_default:
            settings = dict(project.settings or {}); settings["production_default"] = {"generation_type_id": body.generation_type_id, "workflow_version_id": pending[0]["workflow_version_id"]}; project.settings = settings; project.lock_version += 1
        _audit(db, owner_id, "short_drama.production.create", project_id, f"shots={len(pending)};batch={batch.id}")
        db.commit(); db.refresh(batch)
        for item in links: db.refresh(item)
    else:
        existing_ids = {item.id for item in existing_tasks}; links = db.query(ShotTaskLink).filter(ShotTaskLink.owner_id == owner_id, ShotTaskLink.task_id.in_(existing_ids)).all() if existing_ids else []
    return batch, created, existing_tasks, links


def mark_output_payload(db: Session, task_id: int, payload: dict[str, Any]) -> None:
    links = db.query(ShotTaskLink).filter(ShotTaskLink.task_id == task_id).all()
    for link in links: link.output_payload = deepcopy(payload); link.status = "collecting"; link.sync_error = None
    db.commit()


def mark_sync_failed(db: Session, task_id: int, error: str, status: str = "sync_failed") -> None:
    links = db.query(ShotTaskLink).filter(ShotTaskLink.task_id == task_id).all()
    for link in links:
        link.status = status; link.sync_error = error[:4000]; link.sync_attempts += 1
        link.next_retry_at = _now() + timedelta(seconds=min(300, 10 * (2 ** min(link.sync_attempts, 5))))
    db.commit()


def _auto_adopt_director_frame(db: Session, shot: Shot, take: Take) -> None:
    """Director keyframe outputs adopt automatically; video keeps the candidate flow."""
    db.query(Take).filter(Take.shot_id == shot.id, Take.scope == take.scope, Take.is_selected.is_(True)).update(
        {Take.is_selected: False, Take.status: "candidate"}, synchronize_session=False)
    take.is_selected = True; take.status = "selected"
    if take.scope == "start": shot.first_frame_resource_id = take.resource_id
    elif take.scope == "end": shot.last_frame_resource_id = take.resource_id


def reconcile_task_outputs(db: Session, task_id: int) -> list[Take]:
    task = db.get(Task, task_id); links = db.query(ShotTaskLink).filter(ShotTaskLink.task_id == task_id).all()
    if not task or not links: return []
    if task.status == "FAILED":
        for link in links: link.status = "failed"; link.sync_error = task.error; link.next_retry_at = None
        db.commit(); return []
    if task.status != "SUCCESS": raise ProductionValidationError("任务尚未成功，不能回写 Take")
    outputs = db.query(Resource).join(TaskResource, TaskResource.resource_id == Resource.id).filter(TaskResource.task_id == task.id, TaskResource.role == "output", Resource.deleted_at.is_(None)).order_by(TaskResource.id).all()
    if not outputs:
        raise ProductionValidationError("任务成功但暂未登记输出素材")
    created: list[Take] = []
    input_ids = [row[0] for row in db.query(TaskResource.resource_id).filter(TaskResource.task_id == task.id, TaskResource.role == "input").all()]
    for link in links:
        shot = db.get(Shot, link.shot_id)
        if not shot: raise ProductionValidationError("镜头已不存在，无法回写 Take")
        director_scope = str((task.params or {}).get("__director", {}).get("scope") or "video")
        for resource in outputs:
            take = db.query(Take).filter(Take.source_task_id == task.id, Take.resource_id == resource.id).first()
            if not take:
                next_no = (db.query(func.max(Take.take_no)).filter(Take.shot_id == shot.id).scalar() or 0) + 1
                take = Take(owner_id=link.owner_id, shot_id=shot.id, scope=director_scope, resource_id=resource.id, source_task_id=task.id, take_no=next_no, status="candidate", generation_snapshot={"generation_type_id": task.generation_type_id, "workflow_version_id": task.workflow_version_id, "config_version_id": task.config_version_id, "params": deepcopy(task.params or {}), "input_resource_ids": input_ids, "output": {"resource_id": resource.id, "filename": resource.filename, "media_type": resource.media_type, "width": resource.width, "height": resource.height, "duration": resource.duration}})
                db.add(take); db.flush(); created.append(take)
            if link.take_id is None: link.take_id = take.id
            # 关键帧产物自动采用为当前帧，视频保持候选确认流程。
            if director_scope != "video" and resource.media_type == "image" and not take.is_selected:
                _auto_adopt_director_frame(db, shot, take)
        link.status = "synced"; link.sync_error = None; link.next_retry_at = None
    db.commit()
    for item in created: db.refresh(item)
    return created


def _take_out(db: Session, take: Take) -> dict[str, Any]:
    resource = db.get(Resource, take.resource_id)
    return {"id": take.id, "owner_id": take.owner_id, "shot_id": take.shot_id, "resource_id": take.resource_id, "source_task_id": take.source_task_id, "take_no": take.take_no, "status": take.status, "is_selected": take.is_selected, "generation_snapshot": take.generation_snapshot or {}, "review_note": take.review_note, "resource": {"id": resource.id, "filename": resource.filename, "media_type": resource.media_type, "mime": resource.mime, "width": resource.width, "height": resource.height, "duration": resource.duration, "size": resource.size}, "created_at": take.created_at, "updated_at": take.updated_at}


def production_overview(db: Session, owner_id: int, project_id: int, shot_id: int) -> tuple[Shot, list[dict[str, Any]], list[dict[str, Any]]]:
    shot = storyboard_service._owned_shot(db, owner_id, project_id, shot_id)
    links = db.query(ShotTaskLink).filter(ShotTaskLink.owner_id == owner_id, ShotTaskLink.shot_id == shot.id).order_by(ShotTaskLink.id.desc()).all()
    tasks = []
    for link in links:
        task = db.get(Task, link.task_id)
        if task: tasks.append({"link": link, "task_status": task.status, "task_error": task.error, "generation_type_id": task.generation_type_id, "workflow_version_id": task.workflow_version_id, "params": task.params or {}, "created_at": task.created_at})
    takes = [_take_out(db, item) for item in db.query(Take).filter(Take.owner_id == owner_id, Take.shot_id == shot.id).order_by(Take.take_no).all()]
    return shot, tasks, takes


def _owned_take(db: Session, owner_id: int, project_id: int, take_id: int) -> Take:
    take = db.query(Take).join(Shot, Shot.id == Take.shot_id).join(Scene, Scene.id == Shot.scene_id).join(Episode, Episode.id == Scene.episode_id).filter(Take.id == take_id, Take.owner_id == owner_id, Episode.project_id == project_id).first()
    if not take: raise project_service.ProjectNotFoundError("Take 不存在")
    return take


def select_take(db: Session, owner_id: int, project_id: int, take_id: int, selected: bool) -> Take:
    take = _owned_take(db, owner_id, project_id, take_id)
    if take.is_selected == selected: return take
    if selected:
        db.query(Take).filter(Take.shot_id == take.shot_id, Take.scope == take.scope, Take.is_selected.is_(True)).update({Take.is_selected: False, Take.status: "candidate"}, synchronize_session=False); db.flush()
        take.is_selected = True; take.status = "selected"
    else: take.is_selected = False; take.status = "candidate"
    if take.scope in {"start", "end"}:
        shot = db.get(Shot, take.shot_id)
        field = "first_frame_resource_id" if take.scope == "start" else "last_frame_resource_id"
        if selected or getattr(shot, field) == take.resource_id:
            setattr(shot, field, take.resource_id if selected else None)
            shot.lock_version += 1
    db.commit(); db.refresh(take); return take


def review_take(db: Session, owner_id: int, project_id: int, take_id: int, note: str) -> Take:
    take = _owned_take(db, owner_id, project_id, take_id); take.review_note = note; db.commit(); db.refresh(take); return take


def delete_take(db: Session, owner_id: int, project_id: int, take_id: int) -> None:
    take = _owned_take(db, owner_id, project_id, take_id)
    if take.is_selected: raise ProductionValidationError("已采用 Take 不能删除，请先取消采用")
    for link in db.query(ShotTaskLink).filter(ShotTaskLink.take_id == take.id).all(): link.take_id = None
    db.delete(take); db.commit()


def regenerate_take(db: Session, owner_id: int, project_id: int, take_id: int, note: str, overrides: dict[str, Any], idempotency_key: str) -> tuple[Task, ShotTaskLink]:
    take = _owned_take(db, owner_id, project_id, take_id); source = db.get(Task, take.source_task_id) if take.source_task_id else None
    if not source: raise ProductionValidationError("Take 缺少来源任务，不能按原参数重新生成")
    key = f"shot:{take.shot_id}:{idempotency_key}"; existing = db.query(ShotTaskLink).filter(ShotTaskLink.owner_id == owner_id, ShotTaskLink.idempotency_key == key).first()
    if existing: return db.get(Task, existing.task_id), existing
    batch = Batch(user_id=owner_id, name=f"镜头 #{take.shot_id} 返工", generation_type_id=source.generation_type_id, workflow_version_id=source.workflow_version_id, global_params={}, source="short_drama", submitted_at=_now()); db.add(batch); db.flush()
    params = deepcopy(source.params or {}); params.update(overrides); task = Task(batch_id=batch.id, row_no=0, user_id=owner_id, generation_type_id=source.generation_type_id, workflow_version_id=source.workflow_version_id, config_version_id=source.config_version_id, params=params, status="PENDING"); db.add(task); db.flush()
    link = ShotTaskLink(owner_id=owner_id, shot_id=take.shot_id, task_id=task.id, purpose="regenerate", status="linked", idempotency_key=key); db.add(link); take.review_note = note
    db.commit(); db.refresh(task); db.refresh(link); return task, link
