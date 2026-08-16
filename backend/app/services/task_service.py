"""任务服务：查询、取消、重试、事件时间线。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session

from app.models import GenerationType, Task, TaskEvent, TaskResource, WorkflowVersion
from app.services.generation_type_service import normalize_param_template


def _database_datetime(value: datetime | None) -> datetime | None:
    """Convert an API timezone-aware boundary to the naive UTC used by DB columns."""
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def list_tasks(
    db: Session,
    status_: Optional[str] = None,
    batch_id: Optional[int] = None,
    generation_type_id: Optional[int] = None,
    active: bool = False,
    created_from: Optional[datetime] = None,
    created_to: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
    user_id: Optional[int] = None,
    keyword: Optional[str] = None,
) -> tuple[list[Task], int]:
    q = db.query(Task)
    if user_id is not None:
        q = q.filter(Task.user_id == user_id)
    if status_:
        q = q.filter(Task.status == status_)
    if batch_id:
        q = q.filter(Task.batch_id == batch_id)
    if generation_type_id:
        q = q.filter(Task.generation_type_id == generation_type_id)
    if active:
        q = q.filter(Task.status.in_(["PENDING", "DISPATCHING", "QUEUED", "RUNNING", "FINALIZING"]))
    if keyword and keyword.strip():
        pattern = f"%{keyword.strip()}%"
        q = q.filter(or_(
            cast(Task.id, String).ilike(pattern),
            cast(Task.batch_id, String).ilike(pattern),
            Task.params["prompt"].as_string().ilike(pattern),
            Task.error.ilike(pattern),
        ))
    created_from = _database_datetime(created_from)
    created_to = _database_datetime(created_to)
    if created_from:
        q = q.filter(Task.created_at >= created_from)
    if created_to:
        q = q.filter(Task.created_at < created_to)
    total = q.count()
    return q.order_by(Task.id.desc()).offset(offset).limit(limit).all(), total


def get(db: Session, tid: int) -> Optional[Task]:
    return db.get(Task, tid)


def cancel(db: Session, t: Task) -> None:
    if t.status in ("PENDING", "DISPATCHING", "QUEUED", "RUNNING", "FINALIZING"):
        t.status = "CANCELLED"
        db.commit()


def retry(db: Session, t: Task) -> None:
    if t.status in ("FAILED", "CANCELLED"):
        t.status = "PENDING"
        t.error = None
        t.node_id = None
        t.prompt_id = None
        db.commit()


def regenerate(db: Session, t: Task) -> Task:
    if t.status not in ("SUCCESS", "FAILED"):
        raise ValueError("仅已完成或失败的任务可以重新生成")
    regenerated = Task(
        batch_id=t.batch_id,
        row_no=t.row_no,
        user_id=t.user_id,
        generation_type_id=t.generation_type_id,
        workflow_version_id=t.workflow_version_id,
        config_version_id=t.config_version_id,
        params=dict(t.params or {}),
        status="PENDING",
        priority=t.priority,
    )
    db.add(regenerated)
    db.commit()
    db.refresh(regenerated)
    return regenerated


def execute_with_params(db: Session, t: Task, params: dict) -> Task:
    """Create a new queued task from an existing task without mutating the source."""
    executed_params = dict(params or {})
    workflow_version = db.get(WorkflowVersion, t.workflow_version_id) if t.workflow_version_id else None
    schema = workflow_version.param_schema if workflow_version and workflow_version.param_schema else []
    if not schema and t.generation_type_id:
        generation_type = db.get(GenerationType, t.generation_type_id)
        schema = normalize_param_template(generation_type.param_template, generation_type.code) if generation_type else []
    for spec in schema:
        if spec.get("type") in ("image", "video", "audio"):
            key = spec.get("key")
            if key in (t.params or {}):
                executed_params[key] = t.params[key]
            else:
                executed_params.pop(key, None)
    if workflow_version and workflow_version.param_schema:
        from app.services import workflow_service
        executed_params, errors = workflow_service.validate_task_params(
            db, workflow_version, executed_params, t.user_id
        )
        if errors:
            raise ValueError("；".join(errors))
    executed = Task(
        batch_id=t.batch_id,
        row_no=t.row_no,
        user_id=t.user_id,
        generation_type_id=t.generation_type_id,
        workflow_version_id=t.workflow_version_id,
        config_version_id=t.config_version_id,
        params=executed_params,
        status="PENDING",
        priority=t.priority,
    )
    db.add(executed)
    db.commit()
    db.refresh(executed)
    return executed


def delete_task(db: Session, t: Task) -> None:
    """Delete a task record in every lifecycle state while preserving assets.

    A running task may still finish inside ComfyUI, but removing it from the
    console first marks it cancelled so the dispatcher will no longer finalize
    or mutate the record. Task events and resource links are internal children
    and are always removed with the task; physical resource files remain.
    """
    try:
        if t.status in ("PENDING", "DISPATCHING", "QUEUED", "RUNNING", "FINALIZING"):
            t.status = "CANCELLED"
            db.flush()
        db.query(TaskResource).filter(TaskResource.task_id == t.id).delete(synchronize_session=False)
        db.query(TaskEvent).filter(TaskEvent.task_id == t.id).delete(synchronize_session=False)
        db.delete(t)
        db.commit()
    except Exception:
        db.rollback()
        raise


def delete_draft(db: Session, t: Task) -> None:
    """Backward-compatible alias; V2 now permits deleting every inactive task."""
    delete_task(db, t)


def events(db: Session, t: Task) -> list[TaskEvent]:
    return sorted(t.events, key=lambda x: x.created_at)
