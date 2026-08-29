"""短剧编排候选、人工草稿和不可变版本管理。"""
from __future__ import annotations

try:  # Python 3.11+
    from datetime import UTC  # type: ignore[attr-defined]
except ImportError:  # Python 3.10 fallback
    from datetime import timezone as _tz
    UTC = _tz.utc  # type: ignore[assignment]
from datetime import datetime
from math import floor
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AdaptationCandidate,
    AuditLog,
    Episode,
    Scene,
    ShortDramaProject,
    SourceChapter,
    SourceDocument,
    SourceParagraph,
    StoryVersion,
)
from app.schemas.short_drama import EpisodeCreateIn, EpisodePatchIn, SceneCreateIn, ScenePatchIn
from app.short_drama import project_service


class ScreenplayValidationError(ValueError):
    pass


STRATEGIES = (
    ("faithful", "忠实原作", "保留原文信息密度和事件顺序", 1.0),
    ("balanced", "均衡改编", "兼顾原作完整度与短剧节奏", 0.9),
    ("high_tempo", "高节奏", "强化冲突推进和段尾钩子", 0.72),
    ("suspense", "悬念优先", "突出信息差、伏笔和反转节点", 0.82),
    ("emotional", "情感优先", "突出关系变化与情绪递进", 0.88),
)
ELEMENT_TYPES = {"action", "dialogue", "narration", "transition"}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _audit(db: Session, owner_id: int, action: str, project_id: int, detail: str = "") -> None:
    db.add(AuditLog(user_id=owner_id, action=action, target_type="short_drama_project", target_id=project_id, detail=detail or None))


def _owned_document(db: Session, owner_id: int, project_id: int, document_id: int) -> SourceDocument:
    document = db.query(SourceDocument).options(
        selectinload(SourceDocument.chapters).selectinload(SourceChapter.paragraphs)
    ).filter(
        SourceDocument.id == document_id,
        SourceDocument.owner_id == owner_id,
        SourceDocument.project_id == project_id,
    ).first()
    if not document:
        raise project_service.ProjectNotFoundError("源文档不存在")
    if document.status != "ready":
        raise ScreenplayValidationError("源文档尚未解析完成")
    return document


def source_content(
    db: Session, owner_id: int, project_id: int, document_id: int, chapter_start: int | None, chapter_end: int | None
) -> tuple[SourceDocument, list[SourceChapter]]:
    project_service.owned_project(db, owner_id, project_id)
    document = _owned_document(db, owner_id, project_id, document_id)
    chapters = [item for item in document.chapters if (chapter_start is None or item.number >= chapter_start) and (chapter_end is None or item.number <= chapter_end)]
    if not chapters:
        raise ScreenplayValidationError("选择范围内没有章节")
    return document, chapters


def _paragraph_element(text: str) -> dict[str, Any]:
    for separator in ("：", ":"):
        if separator in text:
            speaker, dialogue = text.split(separator, 1)
            if 0 < len(speaker.strip()) <= 12 and dialogue.strip():
                return {"type": "dialogue", "speaker": speaker.strip(), "text": dialogue.strip()}
    return {"type": "action", "text": text}


def _base_episodes(chapters: list[SourceChapter], requested_count: int, duration: int, strategy: str, ratio: float) -> list[dict[str, Any]]:
    count = max(1, min(requested_count, len(chapters)))
    episodes: list[dict[str, Any]] = []
    for index in range(count):
        start = floor(index * len(chapters) / count)
        end = floor((index + 1) * len(chapters) / count)
        group = chapters[start:end]
        scenes: list[dict[str, Any]] = []
        for chapter in group:
            paragraphs = list(chapter.paragraphs)
            content = "\n\n".join(item.text for item in paragraphs)
            references = [{
                "document_id": chapter.document_id,
                "chapter_number": chapter.number,
                "paragraph_start": paragraphs[0].paragraph_index if paragraphs else 1,
                "paragraph_end": paragraphs[-1].paragraph_index if paragraphs else 1,
            }]
            scenes.append({
                "heading": chapter.title or f"第 {chapter.number} 章",
                "location_name": "",
                "time_of_day": "",
                "interior_exterior": "",
                "content": content,
                "elements": [_paragraph_element(item.text) for item in paragraphs],
                "source_references": references,
                "character_ids": [],
                "location_id": None,
                "purpose": f"{strategy}：承接原作第 {chapter.number} 章",
                "target_duration": max(10, round(duration * ratio / max(1, len(group)))),
            })
        episodes.append({
            "title": f"第 {index + 1} 集",
            "synopsis": " / ".join((item.title or f"第 {item.number} 章") for item in group),
            "target_duration": max(10, round(duration * ratio)),
            "scenes": scenes,
        })
    return episodes


def _validate_option(option: dict[str, Any], document: SourceDocument) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    episodes = option.get("episodes")
    if not isinstance(episodes, list) or not episodes:
        return [{"path": "episodes", "message": "至少需要一个分集"}]
    chapter_map = {chapter.number: chapter for chapter in document.chapters}
    for episode_index, episode in enumerate(episodes):
        if not isinstance(episode, dict):
            errors.append({"path": f"episodes[{episode_index}]", "message": "分集必须是对象"})
            continue
        scenes = episode.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            errors.append({"path": f"episodes[{episode_index}].scenes", "message": "分集至少需要一个场景"})
            continue
        for scene_index, scene in enumerate(scenes):
            path = f"episodes[{episode_index}].scenes[{scene_index}]"
            if not isinstance(scene, dict):
                errors.append({"path": path, "message": "场景必须是对象"})
                continue
            if not isinstance(scene.get("heading"), str) or not scene["heading"].strip():
                errors.append({"path": f"{path}.heading", "message": "场景标题不能为空"})
            elements = scene.get("elements", [])
            if not isinstance(elements, list):
                elements = []
            for element_index, element in enumerate(elements):
                if not isinstance(element, dict):
                    errors.append({"path": f"{path}.elements[{element_index}]", "message": "元素必须是对象"})
                    continue
                if element.get("type") not in ELEMENT_TYPES or not str(element.get("text", "")).strip():
                    errors.append({"path": f"{path}.elements[{element_index}]", "message": "元素类型或文本无效"})
            references = scene.get("source_references", [])
            if not isinstance(references, list):
                references = []
            for ref_index, reference in enumerate(references):
                if not isinstance(reference, dict):
                    errors.append({"path": f"{path}.source_references[{ref_index}]", "message": "引用必须是对象"})
                    continue
                ref_doc_id = reference.get("document_id")
                chapter = chapter_map.get(reference.get("chapter_number"))
                # document_id 缺省时视为当前文档；只有显式错误或章节不存在才报错
                if (ref_doc_id is not None and ref_doc_id != document.id) or not chapter:
                    errors.append({"path": f"{path}.source_references[{ref_index}]", "message": "原文引用不存在"})
                    continue
                maximum = len(chapter.paragraphs)
                if not (1 <= int(reference.get("paragraph_start", 0)) <= int(reference.get("paragraph_end", 0)) <= maximum):
                    errors.append({"path": f"{path}.source_references[{ref_index}]", "message": "原文段落范围无效"})
    return errors


def create_candidate(
    db: Session, owner_id: int, project_id: int, document_id: int, chapter_start: int, chapter_end: int, episode_count: int | None
) -> AdaptationCandidate:
    project = project_service.owned_project(db, owner_id, project_id)
    document = _owned_document(db, owner_id, project_id, document_id)
    if chapter_start > chapter_end:
        raise ScreenplayValidationError("起始章节不能大于结束章节")
    chapters = [item for item in document.chapters if chapter_start <= item.number <= chapter_end]
    if not chapters or chapters[0].number != chapter_start or chapters[-1].number != chapter_end:
        raise ScreenplayValidationError("章节范围不完整")
    target_count = episode_count or (project.brief.episode_count if project.brief else 1)
    duration = project.brief.episode_duration if project.brief else 60
    options = [{
        "key": key,
        "label": label,
        "description": description,
        "metrics": {"episode_count": min(target_count, len(chapters)), "source_chapters": len(chapters), "pace_ratio": ratio},
        "episodes": _base_episodes(chapters, target_count, duration, key, ratio),
    } for key, label, description, ratio in STRATEGIES]
    errors = [{"option": option["key"], **error} for option in options for error in _validate_option(option, document)]
    candidate = AdaptationCandidate(
        owner_id=owner_id, project_id=project_id, document_id=document_id,
        chapter_start=chapter_start, chapter_end=chapter_end,
        status="pending", options=options, validation_errors=errors,
    )
    db.add(candidate)
    _audit(db, owner_id, "short_drama.adaptation.preview", project_id, f"document={document_id}; chapters={chapter_start}-{chapter_end}")
    db.commit()
    db.refresh(candidate)
    return candidate


def owned_candidate(db: Session, owner_id: int, project_id: int, candidate_id: int) -> AdaptationCandidate:
    candidate = db.query(AdaptationCandidate).filter(
        AdaptationCandidate.id == candidate_id,
        AdaptationCandidate.owner_id == owner_id,
        AdaptationCandidate.project_id == project_id,
    ).first()
    if not candidate:
        raise project_service.ProjectNotFoundError("改编候选不存在")
    return candidate


def _serialize_episodes(episodes: list[Episode]) -> list[dict[str, Any]]:
    return [{
        "title": episode.title, "synopsis": episode.synopsis, "target_duration": episode.target_duration,
        "core_conflict": episode.core_conflict, "emotional_arc": episode.emotional_arc,
        "opening_hook": episode.opening_hook, "ending_hook": episode.ending_hook, "is_locked": episode.is_locked,
        "scenes": [{
            "heading": scene.heading, "location_name": scene.location_name, "time_of_day": scene.time_of_day,
            "interior_exterior": scene.interior_exterior, "content": scene.content,
            "elements": list(scene.elements or []), "source_references": list(scene.source_references or []),
            "character_ids": list(scene.character_ids or []), "location_id": scene.location_id,
            "purpose": scene.purpose, "target_duration": scene.target_duration,
        } for scene in episode.scenes],
    } for episode in episodes]


def _replace_active(db: Session, project: ShortDramaProject, episodes_payload: list[dict[str, Any]]) -> list[Episode]:
    existing_episodes = list(project.episodes)
    episode_ids = [item.id for item in existing_episodes]
    if episode_ids:
        db.query(Scene).filter(Scene.episode_id.in_(episode_ids)).delete(synchronize_session=False)
        db.query(Episode).filter(Episode.id.in_(episode_ids)).delete(synchronize_session=False)
        db.flush()
        for existing_episode in existing_episodes:
            for existing_scene in list(existing_episode.scenes):
                if existing_scene in db:
                    db.expunge(existing_scene)
            if existing_episode in db:
                db.expunge(existing_episode)
    created: list[Episode] = []
    for episode_index, payload in enumerate(episodes_payload, start=1):
        episode = Episode(
            owner_id=project.owner_id, project_id=project.id, number=episode_index, sort_order=episode_index,
            title=str(payload.get("title", f"第 {episode_index} 集"))[:160], synopsis=str(payload.get("synopsis", "")),
            target_duration=int(payload.get("target_duration", 60)), status="draft",
            core_conflict=str(payload.get("core_conflict", "")), emotional_arc=str(payload.get("emotional_arc", "")),
            opening_hook=str(payload.get("opening_hook", "")), ending_hook=str(payload.get("ending_hook", "")),
            is_locked=bool(payload.get("is_locked", False)),
        )
        db.add(episode); db.flush()
        for scene_index, scene_payload in enumerate(payload.get("scenes", []), start=1):
            db.add(Scene(
                owner_id=project.owner_id, episode_id=episode.id, scene_no=f"{episode_index}-{scene_index}",
                heading=str(scene_payload.get("heading", f"场景 {scene_index}"))[:255],
                location_name=str(scene_payload.get("location_name", ""))[:160], time_of_day=str(scene_payload.get("time_of_day", ""))[:64],
                interior_exterior=str(scene_payload.get("interior_exterior", ""))[:16], content=str(scene_payload.get("content", "")),
                elements=list(scene_payload.get("elements", [])), source_references=list(scene_payload.get("source_references", [])),
                character_ids=list(scene_payload.get("character_ids", [])), location_id=scene_payload.get("location_id"),
                purpose=str(scene_payload.get("purpose", "")), target_duration=int(scene_payload.get("target_duration", 0)),
                sort_order=scene_index, status="draft",
            ))
        created.append(episode)
    db.flush()
    return created


def _create_version(
    db: Session, project: ShortDramaProject, name: str, source: str, content: dict[str, Any], parent_id: int | None = None
) -> StoryVersion:
    db.query(StoryVersion).filter(StoryVersion.project_id == project.id, StoryVersion.is_current.is_(True)).update(
        {StoryVersion.is_current: False}, synchronize_session=False
    )
    number = (db.query(func.max(StoryVersion.version)).filter(StoryVersion.project_id == project.id).scalar() or 0) + 1
    version = StoryVersion(
        owner_id=project.owner_id, project_id=project.id, parent_version_id=parent_id, version=number,
        name=name.strip(), source=source, summary=f"{len(content.get('episodes', []))} 集",
        content=content, is_current=True,
    )
    db.add(version); db.flush()
    return version


def confirm_candidate(
    db: Session, owner_id: int, project_id: int, candidate_id: int, option_key: str, version_name: str
) -> StoryVersion:
    project = project_service.owned_project(db, owner_id, project_id)
    candidate = owned_candidate(db, owner_id, project_id, candidate_id)
    if candidate.status == "confirmed":
        if candidate.confirmed_option == option_key and candidate.confirmed_version_id:
            return db.get(StoryVersion, candidate.confirmed_version_id)  # type: ignore[return-value]
        raise project_service.ProjectConflictError("该候选已经确认，不能改选其他方案")
    if candidate.status != "pending":
        raise ScreenplayValidationError("候选方案当前不可确认")
    option = next((item for item in candidate.options if item.get("key") == option_key), None)
    if not option:
        raise ScreenplayValidationError("改编方案不存在")
    document = _owned_document(db, owner_id, project_id, candidate.document_id)
    errors = _validate_option(option, document)
    if errors:
        candidate.validation_errors = errors
    normalized_episodes = [{
        **episode_payload,
        "core_conflict": episode_payload.get("core_conflict", ""),
        "emotional_arc": episode_payload.get("emotional_arc", ""),
        "opening_hook": episode_payload.get("opening_hook", ""),
        "ending_hook": episode_payload.get("ending_hook", ""),
        "is_locked": bool(episode_payload.get("is_locked", False)),
    } for episode_payload in option["episodes"]]
    _replace_active(db, project, normalized_episodes)
    content = {"episodes": normalized_episodes, "adaptation": {"candidate_id": candidate.id, "option": option_key}}
    version = _create_version(db, project, version_name, "adaptation", content)
    candidate.status = "confirmed"; candidate.confirmed_option = option_key; candidate.confirmed_version_id = version.id
    project.stage = "screenplay"; project.lock_version += 1
    _audit(db, owner_id, "short_drama.adaptation.confirm", project_id, f"candidate={candidate.id}; option={option_key}; version={version.id}")
    # V3 场景台账稳定键对齐 + 步骤 2 门禁通过（模块关闭或异常时静默跳过，不影响主流程）
    try:
        from app.config import settings as _settings
        if getattr(_settings, "v3_director_enabled", False):
            from app.short_drama.v3_director import director_workflow_service, scene_ledger_service
            scene_ledger_service.sync_scenes_from_story_version(db, project.id, version.id, normalized_episodes)
            # 确认改编候选即视为步骤 2（改编候选确认）通过
            director_workflow_service.set_gate(db, project.id, 2, "passed")
    except Exception:  # noqa: BLE001
        pass
    db.commit(); db.refresh(version)
    return version


def screenplay(db: Session, owner_id: int, project_id: int) -> tuple[ShortDramaProject, list[Episode], StoryVersion | None, bool]:
    project = db.query(ShortDramaProject).options(
        selectinload(ShortDramaProject.episodes).selectinload(Episode.scenes)
    ).filter(ShortDramaProject.id == project_id, ShortDramaProject.owner_id == owner_id, ShortDramaProject.deleted_at.is_(None)).first()
    if not project:
        raise project_service.ProjectNotFoundError("短剧项目不存在")
    current = db.query(StoryVersion).filter(StoryVersion.project_id == project_id, StoryVersion.owner_id == owner_id, StoryVersion.is_current.is_(True)).first()
    active = _serialize_episodes(project.episodes)
    changed = bool(current and current.content.get("episodes") != active)
    return project, project.episodes, current, changed


def _owned_episode(db: Session, owner_id: int, project_id: int, episode_id: int) -> Episode:
    episode = db.query(Episode).filter(Episode.id == episode_id, Episode.owner_id == owner_id, Episode.project_id == project_id).first()
    if not episode:
        raise project_service.ProjectNotFoundError("分集不存在")
    return episode


def _owned_scene(db: Session, owner_id: int, project_id: int, scene_id: int) -> tuple[Episode, Scene]:
    result = db.query(Episode, Scene).join(Scene, Scene.episode_id == Episode.id).filter(
        Episode.project_id == project_id, Episode.owner_id == owner_id, Scene.owner_id == owner_id, Scene.id == scene_id
    ).first()
    if not result:
        raise project_service.ProjectNotFoundError("场景不存在")
    return result


def create_episode(db: Session, owner_id: int, project_id: int, body: EpisodeCreateIn) -> Episode:
    project_service.owned_project(db, owner_id, project_id)
    maximum = db.query(func.max(Episode.number)).filter(Episode.project_id == project_id).scalar() or 0
    episode = Episode(owner_id=owner_id, project_id=project_id, number=maximum + 1, sort_order=maximum + 1, status="draft", **body.model_dump())
    db.add(episode); db.commit(); db.refresh(episode)
    return episode


def update_episode(db: Session, owner_id: int, project_id: int, episode_id: int, body: EpisodePatchIn) -> Episode:
    episode = _owned_episode(db, owner_id, project_id, episode_id)
    if episode.lock_version != body.lock_version:
        raise project_service.ProjectConflictError("分集已被其他操作修改")
    for field, value in body.model_dump(exclude_unset=True, exclude={"lock_version"}).items():
        setattr(episode, field, value)
    episode.lock_version += 1; db.commit(); db.refresh(episode)
    return episode


def delete_episode(db: Session, owner_id: int, project_id: int, episode_id: int) -> None:
    episode = _owned_episode(db, owner_id, project_id, episode_id)
    db.query(Scene).filter(Scene.episode_id == episode.id).delete(synchronize_session=False)
    db.delete(episode); db.commit()


def create_scene(db: Session, owner_id: int, project_id: int, episode_id: int, body: SceneCreateIn) -> Scene:
    episode = _owned_episode(db, owner_id, project_id, episode_id)
    maximum = db.query(func.max(Scene.sort_order)).filter(Scene.episode_id == episode.id).scalar() or 0
    _validate_manual_scene(db, owner_id, project_id, body.elements, body.source_references, body.character_ids, body.location_id)
    scene = Scene(owner_id=owner_id, episode_id=episode.id, scene_no=f"{episode.number}-{maximum + 1}", sort_order=maximum + 1, status="draft", **body.model_dump())
    db.add(scene); db.commit(); db.refresh(scene)
    return scene


def _validate_manual_scene(db: Session, owner_id: int, project_id: int, elements: list[dict[str, Any]], references: list[dict[str, Any]], character_ids: list[int], location_id: int | None) -> None:
    for index, element in enumerate(elements):
        if element.get("type") not in ELEMENT_TYPES or not str(element.get("text", "")).strip():
            raise ScreenplayValidationError(f"第 {index + 1} 个剧本元素无效")
    for reference in references:
        document = db.query(SourceDocument).filter(
            SourceDocument.id == reference.get("document_id"), SourceDocument.owner_id == owner_id, SourceDocument.project_id == project_id
        ).first()
        if not document:
            raise ScreenplayValidationError("场景引用了不存在的源文档")
        chapter = db.query(SourceChapter).filter(
            SourceChapter.document_id == document.id,
            SourceChapter.number == reference.get("chapter_number"),
            SourceChapter.owner_id == owner_id,
        ).first()
        if not chapter:
            raise ScreenplayValidationError("场景引用了不存在的原文章节")
        paragraph_count = db.query(func.count(SourceParagraph.id)).filter(SourceParagraph.chapter_id == chapter.id).scalar() or 0
        start = int(reference.get("paragraph_start", 0)); end = int(reference.get("paragraph_end", 0))
        if not (1 <= start <= end <= paragraph_count):
            raise ScreenplayValidationError("场景引用的原文段落范围无效")
    if character_ids:
        from app.models import Character
        count = db.query(func.count(Character.id)).filter(Character.owner_id == owner_id, Character.project_id == project_id, Character.id.in_(character_ids)).scalar() or 0
        if count != len(set(character_ids)): raise ScreenplayValidationError("场景引用了不存在的角色")
    if location_id is not None:
        from app.models import Location
        if not db.query(Location.id).filter(Location.id == location_id, Location.owner_id == owner_id, Location.project_id == project_id).first():
            raise ScreenplayValidationError("场景引用了不存在的地点")


def update_scene(db: Session, owner_id: int, project_id: int, scene_id: int, body: ScenePatchIn) -> Scene:
    _, scene = _owned_scene(db, owner_id, project_id, scene_id)
    if scene.lock_version != body.lock_version:
        raise project_service.ProjectConflictError("场景已被其他操作修改")
    changes = body.model_dump(exclude_unset=True, exclude={"lock_version"})
    _validate_manual_scene(db, owner_id, project_id, changes.get("elements", scene.elements), changes.get("source_references", scene.source_references), changes.get("character_ids", scene.character_ids), changes.get("location_id", scene.location_id))
    for field, value in changes.items(): setattr(scene, field, value)
    scene.lock_version += 1; db.commit(); db.refresh(scene)
    return scene


def delete_scene(db: Session, owner_id: int, project_id: int, scene_id: int) -> None:
    _, scene = _owned_scene(db, owner_id, project_id, scene_id)
    db.delete(scene); db.commit()


def reorder(db: Session, owner_id: int, project_id: int, episode_ids: list[int], scene_ids_by_episode: dict[int, list[int]]) -> None:
    episodes = db.query(Episode).filter(Episode.owner_id == owner_id, Episode.project_id == project_id).all()
    if set(episode_ids) != {item.id for item in episodes} or len(episode_ids) != len(set(episode_ids)):
        raise ScreenplayValidationError("分集重排列表必须完整且不能重复")
    for order, episode_id in enumerate(episode_ids, start=1):
        episode = next(item for item in episodes if item.id == episode_id); episode.sort_order = order
        if episode_id in scene_ids_by_episode:
            scenes = db.query(Scene).filter(Scene.episode_id == episode_id, Scene.owner_id == owner_id).all()
            requested = scene_ids_by_episode[episode_id]
            if set(requested) != {item.id for item in scenes} or len(requested) != len(set(requested)):
                raise ScreenplayValidationError("场景重排列表必须完整且不能重复")
            for scene_order, scene_id in enumerate(requested, start=1):
                next(item for item in scenes if item.id == scene_id).sort_order = scene_order
    db.commit()


def create_manual_version(db: Session, owner_id: int, project_id: int, name: str) -> StoryVersion:
    project, episodes, current, _ = screenplay(db, owner_id, project_id)
    content = {"episodes": _serialize_episodes(episodes), "manual_saved_at": _now().isoformat() + "Z"}
    version = _create_version(db, project, name, "manual", content, current.id if current else None)
    _audit(db, owner_id, "short_drama.version.create", project_id, f"version={version.id}")
    db.commit(); db.refresh(version)
    return version


def list_versions(db: Session, owner_id: int, project_id: int) -> list[StoryVersion]:
    project_service.owned_project(db, owner_id, project_id)
    return db.query(StoryVersion).filter(StoryVersion.owner_id == owner_id, StoryVersion.project_id == project_id).order_by(StoryVersion.version.desc()).all()


def owned_version(db: Session, owner_id: int, project_id: int, version_id: int) -> StoryVersion:
    version = db.query(StoryVersion).filter(
        StoryVersion.id == version_id, StoryVersion.owner_id == owner_id, StoryVersion.project_id == project_id
    ).first()
    if not version: raise project_service.ProjectNotFoundError("剧本版本不存在")
    return version


def rename_version(db: Session, owner_id: int, project_id: int, version_id: int, name: str) -> StoryVersion:
    version = owned_version(db, owner_id, project_id, version_id)
    version.name = name.strip(); db.commit(); db.refresh(version)
    return version


def restore_version(db: Session, owner_id: int, project_id: int, version_id: int) -> StoryVersion:
    project = project_service.owned_project(db, owner_id, project_id)
    source = owned_version(db, owner_id, project_id, version_id)
    episodes = source.content.get("episodes")
    if not isinstance(episodes, list): raise ScreenplayValidationError("版本内容损坏，无法恢复")
    _replace_active(db, project, episodes)
    restored = _create_version(db, project, f"恢复自 V{source.version} · {source.name}", "restore", {**source.content, "restored_from": source.id}, source.id)
    _audit(db, owner_id, "short_drama.version.restore", project_id, f"from={source.id}; version={restored.id}")
    db.commit(); db.refresh(restored)
    return restored
