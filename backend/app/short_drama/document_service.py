"""源文档导入、CreativeJob 控制与所有权隔离。"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models import AuditLog, CreativeJob, ProjectResourceLink, SourceDocument
from app.services import resource_service
from app.short_drama import project_service

ALLOWED_SUFFIXES = {".txt", ".docx", ".epub"}
MAX_IMPORT_BYTES = 50 * 1024 * 1024


class DocumentImportError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _log(job: CreativeJob, level: str, message: str) -> None:
    job.logs = [*list(job.logs or []), {"time": _now().isoformat(timespec="seconds") + "Z", "level": level, "message": message}]


def _audit(db: Session, owner_id: int, action: str, project_id: int, detail: str) -> None:
    db.add(AuditLog(user_id=owner_id, action=action, target_type="short_drama_project", target_id=project_id, detail=detail))


async def create_import(db: Session, owner_id: int, project_id: int, file: UploadFile) -> tuple[SourceDocument, CreativeJob]:
    project_service.owned_project(db, owner_id, project_id)
    raw_name = (file.filename or "").replace("\\", "/")
    filename = Path(raw_name).name
    suffix = Path(filename).suffix.lower()
    if not filename or suffix not in ALLOWED_SUFFIXES:
        raise DocumentImportError("仅支持 TXT、DOCX、EPUB 文件")
    content = await file.read(MAX_IMPORT_BYTES + 1)
    if not content:
        raise DocumentImportError("文件内容为空")
    if len(content) > MAX_IMPORT_BYTES:
        raise DocumentImportError("导入文件不能超过 50MB")
    await file.seek(0)
    file.filename = filename
    resource = await resource_service.upload_resource(db, file, owner_id, direction="input", media_type="document")
    idempotency_key = f"story-import:{project_id}:{resource.sha256}"

    document = db.query(SourceDocument).filter(
        SourceDocument.owner_id == owner_id,
        SourceDocument.project_id == project_id,
        SourceDocument.resource_id == resource.id,
    ).first()
    job = db.query(CreativeJob).filter(
        CreativeJob.owner_id == owner_id,
        CreativeJob.idempotency_key == idempotency_key,
    ).first()
    if document and job:
        return document, job

    if not document:
        document = SourceDocument(
            owner_id=owner_id,
            project_id=project_id,
            resource_id=resource.id,
            filename=filename,
            source_format=suffix.lstrip("."),
            title=Path(filename).stem,
            status="pending",
        )
        db.add(document)
        db.flush()
    link = db.query(ProjectResourceLink).filter(
        ProjectResourceLink.owner_id == owner_id,
        ProjectResourceLink.project_id == project_id,
        ProjectResourceLink.resource_id == resource.id,
        ProjectResourceLink.purpose == "source_document",
    ).first()
    if not link:
        db.add(ProjectResourceLink(
            owner_id=owner_id,
            project_id=project_id,
            resource_id=resource.id,
            entity_type="source_document",
            entity_id=document.id,
            purpose="source_document",
            metadata_snapshot={"filename": filename, "format": suffix.lstrip(".")},
        ))
    if not job:
        job = CreativeJob(
            owner_id=owner_id,
            project_id=project_id,
            job_type="parse_document",
            status="queued",
            progress=0,
            idempotency_key=idempotency_key,
            input_payload={"document_id": document.id, "resource_id": resource.id, "filename": filename},
            logs=[],
        )
        _log(job, "info", "文档已进入解析队列")
        db.add(job)
        _audit(db, owner_id, "short_drama.document.import", project_id, f"document={document.id}; filename={filename}")
    db.commit()
    db.refresh(document)
    db.refresh(job)
    return document, job


def list_documents(db: Session, owner_id: int, project_id: int) -> list[SourceDocument]:
    project_service.owned_project(db, owner_id, project_id)
    return db.query(SourceDocument).filter(
        SourceDocument.owner_id == owner_id, SourceDocument.project_id == project_id
    ).order_by(SourceDocument.id.desc()).all()


def owned_job(db: Session, owner_id: int, job_id: int) -> CreativeJob:
    job = db.get(CreativeJob, job_id)
    if not job or job.owner_id != owner_id:
        raise project_service.ProjectNotFoundError("创作任务不存在")
    return job


def list_jobs(
    db: Session, owner_id: int, *, project_id: int | None, status: str | None, page: int, page_size: int
) -> tuple[list[CreativeJob], int]:
    query = db.query(CreativeJob).filter(CreativeJob.owner_id == owner_id)
    if project_id is not None:
        project_service.owned_project(db, owner_id, project_id)
        query = query.filter(CreativeJob.project_id == project_id)
    if status:
        query = query.filter(CreativeJob.status == status)
    total = query.count()
    return query.order_by(CreativeJob.id.desc()).offset((page - 1) * page_size).limit(page_size).all(), total


def cancel_job(db: Session, owner_id: int, job_id: int) -> CreativeJob:
    job = owned_job(db, owner_id, job_id)
    changed = False
    if job.status == "queued":
        changed = True
        job.status = "cancelled"
        job.cancelled_at = _now()
        job.finished_at = job.cancelled_at
        _log(job, "warning", "用户取消了排队任务")
    elif job.status == "running":
        changed = True
        job.status = "cancelling"
        _log(job, "warning", "已请求取消，等待当前解析步骤结束")
    elif job.status not in {"cancelled", "cancelling"}:
        raise DocumentImportError("当前任务状态不能取消")
    if changed and job.project_id is not None:
        _audit(db, owner_id, "short_drama.job.cancel", job.project_id, f"job={job.id}")
    db.commit()
    db.refresh(job)
    return job


def retry_job(db: Session, owner_id: int, job_id: int) -> CreativeJob:
    job = owned_job(db, owner_id, job_id)
    if job.status not in {"failed", "cancelled"}:
        raise DocumentImportError("只有失败或已取消任务可以重试")
    document = None
    if job.job_type == "parse_document":
        document = db.get(SourceDocument, int(job.input_payload.get("document_id", 0)))
        if not document or document.owner_id != owner_id:
            raise project_service.ProjectNotFoundError("源文档不存在")
    job.status = "queued"
    job.progress = 0
    job.error = None
    job.started_at = None
    job.finished_at = None
    job.cancelled_at = None
    job.heartbeat_at = None
    job.retries += 1
    if document:
        document.status = "pending"
        document.error = None
    _log(job, "info", f"任务已重新排队（第 {job.retries} 次重试）")
    if job.project_id is not None:
        _audit(db, owner_id, "short_drama.job.retry", job.project_id, f"job={job.id}; retries={job.retries}")
    db.commit()
    db.refresh(job)
    return job
