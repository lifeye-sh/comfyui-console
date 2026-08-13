"""任务服务：查询、取消、重试、事件时间线。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import GenerationType, Task, TaskEvent, TaskResource


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
    generation_type = db.get(GenerationType, t.generation_type_id) if t.generation_type_id else None
    for spec in (generation_type.param_template if generation_type else []) or []:
        if spec.get("type") in ("image", "video", "audio"):
            key = spec.get("key")
            if key in (t.params or {}):
                executed_params[key] = t.params[key]
            else:
                executed_params.pop(key, None)
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
    if t.status in ("PENDING", "DISPATCHING", "QUEUED", "RUNNING", "FINALIZING"):
        raise ValueError("执行中的任务不能删除，请先取消任务")
    # 删除任务记录但保留素材库文件；产物仍可在日期目录中独立管理。
    db.query(TaskResource).filter(TaskResource.task_id == t.id).delete(synchronize_session=False)
    db.query(TaskEvent).filter(TaskEvent.task_id == t.id).delete(synchronize_session=False)
    db.delete(t)
    db.commit()


def delete_draft(db: Session, t: Task) -> None:
    """Backward-compatible alias; V2 now permits deleting every inactive task."""
    delete_task(db, t)


def events(db: Session, t: Task) -> list[TaskEvent]:
    return sorted(t.events, key=lambda x: x.created_at)
