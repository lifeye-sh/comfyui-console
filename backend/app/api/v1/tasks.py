"""任务路由 /api/v1/tasks。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import CurrentUser, DBSession
from app.models import Task, WorkflowVersion, Workflow
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
    # 批量查询工作流名称
    wv_ids = {t.workflow_version_id for t in items if t.workflow_version_id}
    wv_map: dict[int, str] = {}
    if wv_ids:
        rows = (
            db.query(WorkflowVersion.id, Workflow.name)
            .join(Workflow, WorkflowVersion.workflow_id == Workflow.id)
            .filter(WorkflowVersion.id.in_(wv_ids))
            .all()
        )
        wv_map = {wid: name for wid, name in rows}
    result = []
    for t in items:
        out = TaskOut.model_validate(t)
        if t.workflow_version_id:
            out.workflow_name = wv_map.get(t.workflow_version_id)
        result.append(out)
    return result


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
    result = TaskOut.model_validate(t)
    if t.workflow_version_id:
        from app.models import WorkflowVersion
        version = db.get(WorkflowVersion, t.workflow_version_id)
        result.workflow_param_schema = version.param_schema if version else []
    return result


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
    try:
        executed = task_service.execute_with_params(db, t, body.params)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return TaskOut.model_validate(executed)


@router.delete("/{tid}", status_code=204, response_model=None)
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


@router.post("/{tid}/recheck", response_model=dict)
def recheck_task(tid: int, user: CurrentUser, db: DBSession) -> dict:
    """再检查失败任务：重新获取 ComfyUI history，若找到则回收输出；若仍丢失则按文件名规律搜索输出文件。"""
    import asyncio, hashlib, os
    from app.models import Node, Resource, TaskResource, GenerationType
    from app.services.resource_service import build_image_thumbnail, thumbnail_storage_key
    from app.storage.local_fs import get_storage
    from app.comfy.client import ComfyUIClient

    t = task_service.get(db, tid)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if t.user_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问")
    if t.status != "FAILED":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "仅失败任务可再检查")

    node = db.get(Node, t.node_id) if t.node_id else None
    if not node or not t.prompt_id:
        return {"ok": False, "message": "任务没有关联节点或 Prompt ID，无法再检查", "status": t.status}

    client = ComfyUIClient(node.id, node.base_url, node.ws_url)
    try:
        loop = asyncio.new_event_loop()
        try:
            # 1. 重新获取 history
            hist = loop.run_until_complete(client.get_history(t.prompt_id))
            entry = hist.get(t.prompt_id)
            if entry:
                status_info = entry.get("status", {}) or {}
                if status_info.get("completed"):
                    from app.queue.dispatcher import dispatcher
                    loop2 = asyncio.new_event_loop()
                    try:
                        loop2.run_until_complete(dispatcher._collect_outputs(db, t, client, entry.get("outputs", {})))
                        t.status = "SUCCESS"
                        t.error = None
                        from datetime import datetime as dt
                        t.finished_at = dt.now()
                        db.commit()
                    finally:
                        loop2.close()
                    return {"ok": True, "message": "已找到任务记录并回收输出", "status": "SUCCESS"}
                if status_info.get("status_str") == "error":
                    return {"ok": False, "message": "任务确实执行失败", "status": "FAILED"}

            # 2. history 没找到，按文件名规律搜索 ComfyUI 输出目录
            for prefix in ["", "ComfyUI_"]:
                for i in range(100):
                    for ext, mt in [(".png", "image"), (".mp4", "video"), (".jpg", "image")]:
                        fname = f"{prefix}{i:05d}{ext}"
                        try:
                            data = loop.run_until_complete(client.get_view_bytes(fname, type="output"))
                            if not data or len(data) < 100:
                                continue
                            sha = hashlib.sha256(data).hexdigest()
                            if db.query(Resource).filter(Resource.sha256 == sha, Resource.deleted_at.is_(None)).first():
                                continue
                            key = f"resources/{datetime.now():%Y-%m}/{sha[:16]}/{fname}"
                            get_storage().save_bytes(data, key)
                            tk = None
                            if mt == "image":
                                try:
                                    td, _, _ = build_image_thumbnail(data)
                                    tk = thumbnail_storage_key(key)
                                    get_storage().save_bytes(td, tk)
                                except Exception:
                                    pass
                            from app.services.resource_folder_service import ensure_task_result_folder
                            gt = db.get(GenerationType, t.generation_type_id) if t.generation_type_id else None
                            r = Resource(
                                owner_id=t.user_id,
                                folder_id=ensure_task_result_folder(db, t.user_id, t.id, gt.name if gt else "未知类型").id if t.user_id else None,
                                media_type=mt, direction="output", filename=fname,
                                mime=f"image/{ext[1:]}" if mt == "image" else "video/mp4",
                                size=len(data), sha256=sha, storage_key=key, thumb_key=tk, visibility="private",
                            )
                            db.add(r); db.flush()
                            db.add(TaskResource(task_id=t.id, resource_id=r.id, role="output"))
                            t.status = "SUCCESS"; t.error = None
                            from datetime import datetime as dt
                            t.finished_at = dt.now()
                            db.commit()
                            return {"ok": True, "message": f"通过文件搜索找到输出：{fname}", "status": "SUCCESS"}
                        except Exception:
                            continue
        finally:
            loop.close()
    finally:
        try:
            loop3 = asyncio.new_event_loop()
            loop3.run_until_complete(client.aclose())
            loop3.close()
        except Exception:
            pass

    return {"ok": False, "message": "未找到任务记录或输出文件", "status": t.status}
