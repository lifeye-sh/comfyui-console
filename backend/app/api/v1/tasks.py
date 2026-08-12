"""任务路由 /api/v1/tasks。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import CurrentUser, DBSession
from app.services import task_service
from app.schemas.schemas import TaskEventOut, TaskExecuteIn, TaskOut

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskOut])
def list_(
    user: CurrentUser,
    db: DBSession,
    status: str | None = None,
    batch_id: int | None = None,
    generation_type_id: int | None = None,
    active: bool = False,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[TaskOut]:
    items, _ = task_service.list_tasks(
        db, status, batch_id, generation_type_id, active, created_from, created_to, limit, offset
    )
    return [TaskOut.model_validate(t) for t in items]


@router.get("/{tid}", response_model=TaskOut)
def get_one(tid: int, user: CurrentUser, db: DBSession) -> TaskOut:
    t = task_service.get(db, tid)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    return TaskOut.model_validate(t)


@router.get("/{tid}/events", response_model=list[TaskEventOut])
def events(tid: int, user: CurrentUser, db: DBSession) -> list[TaskEventOut]:
    t = task_service.get(db, tid)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    return [TaskEventOut.model_validate(e) for e in task_service.events(db, t)]


@router.post("/{tid}/cancel", response_model=TaskOut)
def cancel(tid: int, user: CurrentUser, db: DBSession) -> TaskOut:
    t = task_service.get(db, tid)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    task_service.cancel(db, t)
    return TaskOut.model_validate(t)


@router.post("/{tid}/retry", response_model=TaskOut)
def retry(tid: int, user: CurrentUser, db: DBSession) -> TaskOut:
    t = task_service.get(db, tid)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    task_service.retry(db, t)
    return TaskOut.model_validate(t)


@router.post("/{tid}/regenerate", response_model=TaskOut)
def regenerate(tid: int, user: CurrentUser, db: DBSession) -> TaskOut:
    t = task_service.get(db, tid)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    try:
        regenerated = task_service.regenerate(db, t)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return TaskOut.model_validate(regenerated)


@router.post("/{tid}/execute", response_model=TaskOut)
def execute_with_params(tid: int, body: TaskExecuteIn, user: CurrentUser, db: DBSession) -> TaskOut:
    """Copy task execution context and enqueue a new task with edited parameters."""
    t = task_service.get(db, tid)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    executed = task_service.execute_with_params(db, t, body.params)
    return TaskOut.model_validate(executed)


@router.delete("/{tid}", status_code=204)
def delete_draft(tid: int, user: CurrentUser, db: DBSession) -> None:
    t = task_service.get(db, tid)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    try:
        task_service.delete_draft(db, t)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/{tid}/outputs")
def get_outputs(tid: int, user: CurrentUser, db: DBSession) -> list[dict]:
    """获取任务的输出资源列表。"""
    from app.models import TaskResource, Resource
    t = task_service.get(db, tid)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    trs = db.query(TaskResource).filter(
        TaskResource.task_id == tid,
        TaskResource.role == "output",
    ).order_by(TaskResource.id).all()
    result = []
    for tr in trs:
        r = db.get(Resource, tr.resource_id)
        if r and not r.deleted_at:
            result.append({
                "id": r.id,
                "filename": r.filename,
                "mime": r.mime,
                "media_type": r.media_type,
                "thumb_key": r.thumb_key,
                "width": r.width,
                "height": r.height,
            })
    return result
