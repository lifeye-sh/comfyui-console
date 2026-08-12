"""批次路由 /api/v1/batches。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.deps import CurrentUser, DBSession
from app.models import Batch
from app.services import batch_service
from app.schemas.schemas import BatchCreateIn, BatchOut, BatchPatchIn, TaskOut

router = APIRouter(prefix="/batches", tags=["batches"])


@router.post("", response_model=BatchOut, status_code=201)
def create(body: BatchCreateIn, user: CurrentUser, db: DBSession) -> BatchOut:
    b = batch_service.create_batch(db, body, user.id)
    return BatchOut.model_validate(b)


@router.get("", response_model=list[BatchOut])
def list_(
    user: CurrentUser,
    db: DBSession,
    templates: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[BatchOut]:
    items, _ = batch_service.list_batches(db, templates, limit, offset)
    return [BatchOut.model_validate(b) for b in items]


@router.get("/{bid}", response_model=BatchOut)
def get_one(bid: int, user: CurrentUser, db: DBSession) -> BatchOut:
    b = batch_service.get(db, bid)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "批次不存在")
    return BatchOut.model_validate(b)


@router.patch("/{bid}", response_model=BatchOut)
def patch(bid: int, body: BatchPatchIn, user: CurrentUser, db: DBSession) -> BatchOut:
    b = batch_service.get(db, bid)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "批次不存在")
    if b.user_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权修改")
    return BatchOut.model_validate(batch_service.patch_batch(db, b, body.name, body.global_params))


@router.get("/{bid}/rows", response_model=list[TaskOut])
def rows(bid: int, user: CurrentUser, db: DBSession) -> list[TaskOut]:
    b = batch_service.get(db, bid)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "批次不存在")
    return [TaskOut.model_validate(t) for t in sorted(b.tasks, key=lambda x: x.row_no)]


@router.get("/{bid}/status")
def status_(bid: int, user: CurrentUser, db: DBSession) -> dict:
    b = batch_service.get(db, bid)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "批次不存在")
    return batch_service.batch_status_summary(b)


@router.post("/{bid}/submit")
def submit(bid: int, user: CurrentUser, db: DBSession) -> dict:
    b = batch_service.get(db, bid)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "批次不存在")
    if b.user_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权修改")
    return batch_service.submit_batch(db, b)


@router.post("/{bid}/cancel")
def cancel(bid: int, user: CurrentUser, db: DBSession) -> dict:
    b = batch_service.get(db, bid)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "批次不存在")
    return {"cancelled": batch_service.cancel_batch(db, b)}


@router.post("/{bid}/retry-failed")
def retry_failed(bid: int, user: CurrentUser, db: DBSession) -> dict:
    b = batch_service.get(db, bid)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "批次不存在")
    return {"retried": batch_service.retry_failed(db, b)}


@router.post("/{bid}/import")
def import_csv(
    bid: int,
    user: CurrentUser,
    db: DBSession,
    file: UploadFile = File(...),
    start_row: int = 1,
    start_col: int = 1,
    append: bool = False,
) -> dict:
    b = batch_service.get(db, bid)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "批次不存在")
    data = file.file.read()
    return batch_service.import_csv(db, b, user.id, data, start_row, start_col, append)


@router.post("/{bid}/save-template", response_model=BatchOut)
def save_template(bid: int, user: CurrentUser, db: DBSession) -> BatchOut:
    b = batch_service.get(db, bid)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "批次不存在")
    tpl = batch_service.save_as_template(db, b)
    return BatchOut.model_validate(tpl)