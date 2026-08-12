"""批次服务增强：导入任务行、保存模板。"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Batch, GenerationType, Resource, Task, Workflow, WorkflowVersion
from app.schemas.schemas import BatchCreateIn, BatchRowIn


def _version_for_type(db: Session, version_id: int, type_id: Optional[int]) -> Optional[int]:
    version = db.get(WorkflowVersion, version_id)
    if not version:
        return None
    workflow = db.get(Workflow, version.workflow_id)
    if not workflow or (type_id is not None and workflow.generation_type_id != type_id):
        return None
    return version.id


def _resolve_workflow_version(db: Session, batch: Batch, task: Task) -> Optional[int]:
    type_id = task.generation_type_id or batch.generation_type_id
    if task.workflow_version_id:
        return _version_for_type(db, task.workflow_version_id, type_id)
    if batch.workflow_version_id:
        return _version_for_type(db, batch.workflow_version_id, type_id)
    if type_id:
        gt = db.get(GenerationType, type_id)
        if gt and gt.default_workflow_id:
            wf = db.get(Workflow, gt.default_workflow_id)
            if wf and wf.generation_type_id == type_id and wf.current_version_id:
                return _version_for_type(db, wf.current_version_id, type_id)
    return None


def create_batch(db: Session, body: BatchCreateIn, user_id: Optional[int]) -> Batch:
    batch = Batch(
        user_id=user_id,
        name=body.name,
        generation_type_id=body.generation_type_id,
        workflow_version_id=body.workflow_version_id,
        global_params=body.global_params,
        source="manual",
    )
    db.add(batch)
    db.flush()
    for i, row in enumerate(body.rows):
        db.add(_make_task(batch.id, i, row, user_id))
    db.commit()
    db.refresh(batch)
    return batch


def _make_task(batch_id: int, index: int, row: BatchRowIn, user_id: Optional[int]) -> Task:
    return Task(
        batch_id=batch_id,
        row_no=row.row_no if row.row_no is not None else index,
        user_id=user_id,
        generation_type_id=row.generation_type_id,
        workflow_version_id=row.workflow_version_id,
        params=row.params,
        status="DRAFT",
    )


def import_csv(
    db: Session,
    batch: Batch,
    user_id: Optional[int],
    file_bytes: bytes,
    start_row: int = 1,
    start_col: int = 1,
    append: bool = False,
) -> dict:
    """CSV 导入任务行。start_row/start_col 均为 1 开始。"""
    text = file_bytes.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    rows: list[list[str]] = list(reader)

    if not append:
        for t in batch.tasks:
            db.delete(t)

    inserted = 0
    base = len(batch.tasks) if append else 0
    for i, line in enumerate(rows):
        if i + 1 < start_row:
            continue
        col_idx = start_col - 1
        prompt = line[col_idx] if col_idx < len(line) else ""
        # 其他列顺序匹配 param_schema（这里简化：只取 prompt；后续按列名映射）
        row_params = {"prompt": prompt}
        # 如果有 seed/width/height 列，按位置补充
        if col_idx + 1 < len(line):
            row_params["seed"] = int(line[col_idx + 1]) if line[col_idx + 1].isdigit() else 0
        if col_idx + 2 < len(line):
            row_params["width"] = int(line[col_idx + 2]) if line[col_idx + 2].isdigit() else 512
        if col_idx + 3 < len(line):
            row_params["height"] = int(line[col_idx + 3]) if line[col_idx + 3].isdigit() else 512
        t = Task(
            batch_id=batch.id,
            row_no=base + inserted,
            user_id=user_id,
            generation_type_id=batch.generation_type_id,
            params=row_params,
            status="DRAFT",
        )
        db.add(t)
        inserted += 1
    db.commit()
    return {"inserted": inserted}


def submit_batch(db: Session, batch: Batch) -> dict:
    enqueued = 0
    invalid = 0
    for t in batch.tasks:
        if t.status != "DRAFT":
            continue
        wv = _resolve_workflow_version(db, batch, t)
        if not wv:
            t.error = "未配置可用工作流"
            invalid += 1
            continue
        t.workflow_version_id = wv
        t.status = "PENDING"
        t.error = None
        enqueued += 1
    batch.submitted_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "enqueued": enqueued, "invalid": invalid}


def cancel_batch(db: Session, batch: Batch) -> int:
    n = 0
    for t in batch.tasks:
        if t.status in ("PENDING", "DISPATCHING", "QUEUED", "RUNNING"):
            t.status = "CANCELLED"
            n += 1
    db.commit()
    return n


def retry_failed(db: Session, batch: Batch) -> int:
    n = 0
    for t in batch.tasks:
        if t.status == "FAILED":
            t.status = "PENDING"
            t.error = None
            t.retries = 0
            n += 1
    db.commit()
    return n


def save_as_template(db: Session, batch: Batch) -> Batch:
    """复制当前批次（含任务行）为一个模板。"""
    tpl = Batch(
        user_id=batch.user_id,
        name=batch.name + "（模板）",
        generation_type_id=batch.generation_type_id,
        workflow_version_id=batch.workflow_version_id,
        global_params=batch.global_params,
        source="template",
        is_template=True,
    )
    db.add(tpl)
    db.flush()
    for t in batch.tasks:
        db.add(_make_task(tpl.id, t.row_no, BatchRowIn(
            row_no=t.row_no,
            generation_type_id=t.generation_type_id,
            workflow_version_id=t.workflow_version_id,
            params=t.params,
        ), t.user_id))
    db.commit()
    db.refresh(tpl)
    return tpl


def patch_batch(db: Session, batch: Batch, name: Optional[str] = None, global_params: Optional[dict] = None) -> Batch:
    if name is not None:
        batch.name = name
    if global_params is not None:
        batch.global_params = global_params
    db.commit()
    db.refresh(batch)
    return batch


def get(db: Session, bid: int) -> Optional[Batch]:
    return db.get(Batch, bid)


def list_batches(db: Session, templates: bool = False, limit: int = 50, offset: int = 0) -> tuple[list[Batch], int]:
    q = db.query(Batch).filter(Batch.is_template.is_(templates))
    total = q.count()
    return q.order_by(Batch.id.desc()).offset(offset).limit(limit).all(), total


def batch_status_summary(batch: Batch) -> dict:
    counts: dict[str, int] = {}
    for t in batch.tasks:
        counts[t.status] = counts.get(t.status, 0) + 1
    total = len(batch.tasks)
    done = counts.get("SUCCESS", 0)
    failed = counts.get("FAILED", 0)
    cancelled = counts.get("CANCELLED", 0)
    if not total:
        state = "DRAFT"
    elif done + failed + cancelled == total:
        state = "SUCCESS" if done == total else ("FAILED" if failed + cancelled == total else "PARTIAL")
    else:
        state = "RUNNING"
    return {"state": state, "total": total, "success": done, "failed": failed, "cancelled": cancelled}
