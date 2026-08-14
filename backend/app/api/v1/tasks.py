"""任务路由 /api/v1/tasks。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import CurrentUser, DBSession
from app.services import task_service
from app.schemas.schemas import TaskBulkIn, TaskBulkOut, TaskEventOut, TaskExecuteIn, TaskOut

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
    keyword: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[TaskOut]:
    items, _ = task_service.list_tasks(
        db, status, batch_id, generation_type_id, active, created_from, created_to, limit, offset,
        None if user.role == "admin" else user.id, keyword,
    )
    return [TaskOut.model_validate(t) for t in items]


@router.post("/bulk/action", response_model=TaskBulkOut)
def bulk_action(body: TaskBulkIn, user: CurrentUser, db: DBSession) -> TaskBulkOut:
    if body.action not in {"delete", "cancel", "retry", "regenerate"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "不支持的批量操作")
    task_ids = list(dict.fromkeys(body.task_ids))
    succeeded = 0
    failed: list[dict] = []
    created_task_ids: list[int] = []
    for tid in task_ids:
        task = task_service.get(db, tid)
        if not task:
            if body.action == "delete":
                succeeded += 1
                continue
            failed.append({"task_id": tid, "reason": "任务不存在"})
            continue
        if task.user_id != user.id and user.role != "admin":
            failed.append({"task_id": tid, "reason": "无权操作"})
            continue
        try:
            if body.action == "delete":
                task_service.delete_task(db, task)
            elif body.action == "cancel":
                if task.status not in ("PENDING", "DISPATCHING", "QUEUED", "RUNNING", "FINALIZING"):
                    raise ValueError("当前状态不能取消")
                task_service.cancel(db, task)
            elif body.action == "retry":
                if task.status not in ("FAILED", "CANCELLED"):
                    raise ValueError("仅失败或已取消任务可以重试")
                task_service.retry(db, task)
            else:
                created_task_ids.append(task_service.regenerate(db, task).id)
            succeeded += 1
        except Exception as exc:  # noqa: BLE001 — report individual bulk failures and continue
            db.rollback()
            failed.append({"task_id": tid, "reason": str(exc)})
    return TaskBulkOut(action=body.action, requested=len(task_ids), succeeded=succeeded, failed=failed, created_task_ids=created_task_ids)


@router.get("/output-summaries")
def output_summaries(task_ids: str, user: CurrentUser, db: DBSession) -> dict[int, list[dict]]:
    """Return output metadata for a task page without one request per task.

    This endpoint deliberately avoids on-demand ffprobe/thumbnail generation. The
    task list only needs already-known metadata and can request thumbnails lazily.
    """
    from app.models import Resource, Task, TaskResource

    try:
        ids = list(dict.fromkeys(int(value) for value in task_ids.split(",") if value.strip()))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "任务 ID 格式错误") from exc
    if not ids:
        return {}
    if len(ids) > 100:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "单次最多查询 100 个任务")

    permitted = db.query(Task.id).filter(Task.id.in_(ids))
    if user.role != "admin":
        permitted = permitted.filter(Task.user_id == user.id)
    permitted_ids = {row[0] for row in permitted.all()}
    result: dict[int, list[dict]] = {task_id: [] for task_id in permitted_ids}
    if not permitted_ids:
        return result

    rows = (
        db.query(TaskResource.task_id, Resource)
        .join(Resource, Resource.id == TaskResource.resource_id)
        .filter(
            TaskResource.task_id.in_(permitted_ids),
            TaskResource.role == "output",
            Resource.deleted_at.is_(None),
        )
        .order_by(TaskResource.id)
        .all()
    )
    for task_id, resource in rows:
        if len(result[task_id]) >= 3:
            continue
        result[task_id].append({
            "id": resource.id,
            "filename": resource.filename,
            "mime": resource.mime,
            "media_type": resource.media_type,
            "thumb_key": resource.thumb_key,
            "width": resource.width,
            "height": resource.height,
            "duration": resource.duration,
        })
    return result


@router.get("/count")
def count_tasks(
    user: CurrentUser,
    db: DBSession,
    status: str | None = None,
    batch_id: int | None = None,
    generation_type_id: int | None = None,
    active: bool = False,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    keyword: str | None = None,
) -> dict[str, int]:
    _, total = task_service.list_tasks(
        db, status, batch_id, generation_type_id, active, created_from, created_to, 1, 0,
        None if user.role == "admin" else user.id, keyword,
    )
    return {"total": total}


@router.get("/{tid}", response_model=TaskOut)
def get_one(tid: int, user: CurrentUser, db: DBSession) -> TaskOut:
    t = task_service.get(db, tid)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if t.user_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问")
    return TaskOut.model_validate(t)


@router.get("/{tid}/events", response_model=list[TaskEventOut])
def events(tid: int, user: CurrentUser, db: DBSession) -> list[TaskEventOut]:
    t = task_service.get(db, tid)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if t.user_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问")
    return [TaskEventOut.model_validate(e) for e in task_service.events(db, t)]


@router.post("/{tid}/cancel", response_model=TaskOut)
def cancel(tid: int, user: CurrentUser, db: DBSession) -> TaskOut:
    t = task_service.get(db, tid)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if t.user_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作")
    task_service.cancel(db, t)
    return TaskOut.model_validate(t)


@router.post("/{tid}/retry", response_model=TaskOut)
def retry(tid: int, user: CurrentUser, db: DBSession) -> TaskOut:
    t = task_service.get(db, tid)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if t.user_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作")
    task_service.retry(db, t)
    return TaskOut.model_validate(t)


@router.post("/{tid}/regenerate", response_model=TaskOut)
def regenerate(tid: int, user: CurrentUser, db: DBSession) -> TaskOut:
    t = task_service.get(db, tid)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if t.user_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作")
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
    if t.user_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作")
    executed = task_service.execute_with_params(db, t, body.params)
    return TaskOut.model_validate(executed)


@router.delete("/{tid}", status_code=204)
def delete_task(tid: int, user: CurrentUser, db: DBSession) -> None:
    t = task_service.get(db, tid)
    if not t:
        return
    if t.user_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作")
    task_service.delete_task(db, t)


@router.get("/{tid}/outputs")
def get_outputs(tid: int, user: CurrentUser, db: DBSession) -> list[dict]:
    """获取任务的输出资源列表。"""
    from app.models import TaskResource, Resource
    from app.services.resource_service import ensure_media_metadata
    t = task_service.get(db, tid)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if t.user_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问")
    trs = db.query(TaskResource).filter(
        TaskResource.task_id == tid,
        TaskResource.role == "output",
    ).order_by(TaskResource.id).all()
    result = []
    for tr in trs:
        r = db.get(Resource, tr.resource_id)
        if r and not r.deleted_at:
            ensure_media_metadata(db, r)
            result.append({
                "id": r.id,
                "filename": r.filename,
                "mime": r.mime,
                "media_type": r.media_type,
                "thumb_key": r.thumb_key,
                "width": r.width,
                "height": r.height,
                "duration": r.duration,
            })
    return result
