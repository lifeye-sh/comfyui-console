from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.deps import AdminUser, DBSession
from app.models import Task
from app.queue.dispatcher import dispatcher
from app.services import audit_service, task_service

router = APIRouter(prefix="/runtime", tags=["runtime"])


@router.get("/dispatcher")
def dispatcher_status(admin: AdminUser) -> dict:
    return dispatcher.status()


@router.post("/tasks/{task_id}/release")
def release_task(task_id: int, admin: AdminUser, db: DBSession) -> dict:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if task.status not in ("DISPATCHING", "QUEUED", "RUNNING"):
        raise HTTPException(status.HTTP_409_CONFLICT, "只有占用执行槽的任务可以释放")
    task.status = "FAILED"
    task.error = "管理员手动释放执行槽"
    db.commit()
    audit_service.log(db, admin.id, "runtime.task.release", "task", task.id)
    return {"ok": True, "task_id": task.id, "status": task.status}


@router.post("/tasks/{task_id}/resubmit")
def resubmit_task(task_id: int, admin: AdminUser, db: DBSession) -> dict:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    if task.status not in ("FAILED", "CANCELLED"):
        raise HTTPException(status.HTTP_409_CONFLICT, "只有失败或取消任务可以重新提交")
    task_service.retry(db, task)
    audit_service.log(db, admin.id, "runtime.task.resubmit", "task", task.id)
    return {"ok": True, "task_id": task.id, "status": task.status}
