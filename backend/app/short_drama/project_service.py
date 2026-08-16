"""短剧项目、创作简报与项目概览服务。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    CreativeJob,
    Episode,
    ProjectBrief,
    Scene,
    ShortDramaProject,
    Shot,
    ShotTaskLink,
    Take,
    Task,
)
from app.schemas.short_drama import ProjectBriefInput, ProjectBriefPatchIn, ProjectCreateIn, ProjectPatchIn


class ProjectNotFoundError(LookupError):
    pass


class ProjectConflictError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def owned_project(
    db: Session,
    owner_id: int,
    project_id: int,
    *,
    include_deleted: bool = False,
) -> ShortDramaProject:
    query = db.query(ShortDramaProject).filter(
        ShortDramaProject.id == project_id,
        ShortDramaProject.owner_id == owner_id,
    )
    if not include_deleted:
        query = query.filter(ShortDramaProject.deleted_at.is_(None))
    project = query.first()
    if not project:
        raise ProjectNotFoundError("短剧项目不存在")
    return project


def _audit(db: Session, owner_id: int, action: str, project_id: int, detail: str = "") -> None:
    db.add(AuditLog(
        user_id=owner_id,
        action=action,
        target_type="short_drama_project",
        target_id=project_id,
        detail=detail or None,
    ))


def _apply_brief(brief: ProjectBrief, body: ProjectBriefInput) -> None:
    for field, value in body.model_dump().items():
        setattr(brief, field, value)


def create_project(db: Session, owner_id: int, body: ProjectCreateIn) -> ShortDramaProject:
    project = ShortDramaProject(
        owner_id=owner_id,
        name=body.name.strip(),
        synopsis=body.synopsis.strip(),
        source_type=body.source_type,
    )
    brief = ProjectBrief(owner_id=owner_id)
    _apply_brief(brief, body.brief)
    project.brief = brief
    db.add(project)
    db.flush()
    _audit(db, owner_id, "short_drama.project.create", project.id, f"source_type={body.source_type}")
    db.commit()
    db.refresh(project)
    return project


def _count_map(rows: list[tuple[int, int]]) -> dict[int, int]:
    return {int(key): int(value) for key, value in rows}


def list_projects(
    db: Session,
    owner_id: int,
    *,
    keyword: str | None = None,
    status: str | None = None,
    include_deleted: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    query = db.query(ShortDramaProject).filter(ShortDramaProject.owner_id == owner_id)
    query = query.filter(
        ShortDramaProject.deleted_at.is_not(None) if include_deleted else ShortDramaProject.deleted_at.is_(None)
    )
    if keyword and keyword.strip():
        term = f"%{keyword.strip()}%"
        query = query.filter(or_(ShortDramaProject.name.ilike(term), ShortDramaProject.synopsis.ilike(term)))
    if status:
        query = query.filter(ShortDramaProject.status == status)
    total = query.count()
    projects = query.order_by(ShortDramaProject.updated_at.desc(), ShortDramaProject.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    project_ids = [item.id for item in projects]
    if not project_ids:
        return [], total
    episode_counts = _count_map(db.query(Episode.project_id, func.count(Episode.id)).filter(
        Episode.owner_id == owner_id, Episode.project_id.in_(project_ids)
    ).group_by(Episode.project_id).all())
    scene_counts = _count_map(db.query(Episode.project_id, func.count(Scene.id)).join(
        Scene, Scene.episode_id == Episode.id
    ).filter(Episode.owner_id == owner_id, Scene.owner_id == owner_id, Episode.project_id.in_(project_ids)).group_by(
        Episode.project_id
    ).all())
    shot_counts = _count_map(db.query(Episode.project_id, func.count(Shot.id)).join(
        Scene, Scene.episode_id == Episode.id
    ).join(Shot, Shot.scene_id == Scene.id).filter(
        Episode.owner_id == owner_id,
        Scene.owner_id == owner_id,
        Shot.owner_id == owner_id,
        Episode.project_id.in_(project_ids),
    ).group_by(Episode.project_id).all())
    return [
        {
            **{column.name: getattr(project, column.name) for column in ShortDramaProject.__table__.columns},
            "episode_count": episode_counts.get(project.id, 0),
            "scene_count": scene_counts.get(project.id, 0),
            "shot_count": shot_counts.get(project.id, 0),
        }
        for project in projects
    ], total


def update_project(
    db: Session,
    owner_id: int,
    project_id: int,
    body: ProjectPatchIn,
) -> ShortDramaProject:
    project = owned_project(db, owner_id, project_id)
    if project.lock_version != body.lock_version:
        raise ProjectConflictError("项目已被其他操作修改，请刷新后重试")
    changes = body.model_dump(exclude_unset=True, exclude={"lock_version"})
    for field, value in changes.items():
        setattr(project, field, value.strip() if isinstance(value, str) else value)
    project.lock_version += 1
    _audit(db, owner_id, "short_drama.project.update", project.id, f"fields={','.join(changes)}")
    db.commit()
    db.refresh(project)
    return project


def update_brief(
    db: Session,
    owner_id: int,
    project_id: int,
    body: ProjectBriefPatchIn,
) -> ProjectBrief:
    project = owned_project(db, owner_id, project_id)
    brief = project.brief
    if not brief or brief.owner_id != owner_id:
        raise ProjectNotFoundError("创作简报不存在")
    if brief.lock_version != body.lock_version:
        raise ProjectConflictError("创作简报已被其他操作修改，请刷新后重试")
    _apply_brief(brief, ProjectBriefInput(**body.model_dump(exclude={"lock_version"})))
    brief.lock_version += 1
    project.lock_version += 1
    _audit(db, owner_id, "short_drama.brief.update", project.id)
    db.commit()
    db.refresh(brief)
    return brief


def delete_project(db: Session, owner_id: int, project_id: int) -> ShortDramaProject:
    project = owned_project(db, owner_id, project_id)
    active_task = db.query(Task.id).join(ShotTaskLink, ShotTaskLink.task_id == Task.id).join(
        Shot, Shot.id == ShotTaskLink.shot_id
    ).join(Scene, Scene.id == Shot.scene_id).join(Episode, Episode.id == Scene.episode_id).filter(
        Episode.project_id == project.id,
        Task.status.in_(["QUEUED", "SUBMITTED", "RUNNING"]),
    ).first()
    if active_task:
        raise ProjectConflictError("项目存在排队或运行中的生成任务，暂时不能删除")
    active_creative_job = db.query(CreativeJob.id).filter(
        CreativeJob.owner_id == owner_id,
        CreativeJob.project_id == project.id,
        CreativeJob.status.in_(["queued", "running", "cancelling"]),
    ).first()
    if active_creative_job:
        raise ProjectConflictError("项目存在排队、运行或取消中的创作任务，暂时不能删除")
    settings = dict(project.settings or {})
    settings["status_before_delete"] = project.status
    project.settings = settings
    project.status = "archived"
    project.deleted_at = _now()
    project.lock_version += 1
    _audit(db, owner_id, "short_drama.project.delete", project.id)
    db.commit()
    db.refresh(project)
    return project


def restore_project(db: Session, owner_id: int, project_id: int) -> ShortDramaProject:
    project = owned_project(db, owner_id, project_id, include_deleted=True)
    if project.deleted_at is None:
        return project
    settings = dict(project.settings or {})
    project.status = str(settings.pop("status_before_delete", "draft"))
    project.settings = settings
    project.deleted_at = None
    project.lock_version += 1
    _audit(db, owner_id, "short_drama.project.restore", project.id)
    db.commit()
    db.refresh(project)
    return project


def project_overview(db: Session, owner_id: int, project_id: int) -> dict[str, Any]:
    project = owned_project(db, owner_id, project_id)
    episode_ids = db.query(Episode.id).filter(Episode.owner_id == owner_id, Episode.project_id == project.id)
    scene_ids = db.query(Scene.id).filter(Scene.owner_id == owner_id, Scene.episode_id.in_(episode_ids))
    shot_ids = db.query(Shot.id).filter(Shot.owner_id == owner_id, Shot.scene_id.in_(scene_ids))
    return {
        "project": project,
        "brief": project.brief,
        "episode_count": db.query(func.count(Episode.id)).filter(Episode.owner_id == owner_id, Episode.project_id == project.id).scalar() or 0,
        "scene_count": db.query(func.count(Scene.id)).filter(Scene.owner_id == owner_id, Scene.episode_id.in_(episode_ids)).scalar() or 0,
        "shot_count": db.query(func.count(Shot.id)).filter(Shot.owner_id == owner_id, Shot.scene_id.in_(scene_ids)).scalar() or 0,
        "take_count": db.query(func.count(Take.id)).filter(Take.owner_id == owner_id, Take.shot_id.in_(shot_ids)).scalar() or 0,
        "selected_take_count": db.query(func.count(Take.id)).filter(Take.owner_id == owner_id, Take.shot_id.in_(shot_ids), Take.is_selected.is_(True)).scalar() or 0,
        "creative_job_count": db.query(func.count(CreativeJob.id)).filter(CreativeJob.owner_id == owner_id, CreativeJob.project_id == project.id).scalar() or 0,
        "active_job_count": db.query(func.count(CreativeJob.id)).filter(
            CreativeJob.owner_id == owner_id,
            CreativeJob.project_id == project.id,
            CreativeJob.status.in_(["queued", "running", "cancelling"]),
        ).scalar() or 0,
    }
