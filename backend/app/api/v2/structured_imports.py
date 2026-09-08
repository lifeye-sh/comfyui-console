"""Three-stage Markdown import endpoints for short-drama production data."""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.core.deps import CurrentUser, DBSession
from app.schemas.structured_import import StructuredDataType, StructuredImportApplyOut
from app.schemas.structured_import import StructuredImportOut, StructuredImportPreviewOut
from app.short_drama import structured_import_service

router = APIRouter(prefix="/short-drama", tags=["v2-short-drama-structured-imports"])


async def _markdown(file: UploadFile) -> tuple[str, str]:
    if not file.filename or not file.filename.lower().endswith(".md"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请选择Markdown（.md）数据文件")
    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Markdown文件不能超过10MB")
    try:
        return file.filename, raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文件必须使用UTF-8编码") from exc


@router.post("/projects/{project_id}/structured-imports/preview", response_model=StructuredImportPreviewOut)
async def preview_structured_import(
    project_id: int,
    user: CurrentUser,
    db: DBSession,
    data_type: StructuredDataType = Form(...),
    file: UploadFile = File(...),
) -> StructuredImportPreviewOut:
    try:
        structured_import_service.list_imports(db, user.id, project_id)
    except structured_import_service.StructuredImportError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    filename, content = await _markdown(file)
    try:
        parsed = structured_import_service.parse_content(data_type, content)
    except structured_import_service.StructuredImportError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    normalized = content.replace("\r\n", "\n").lstrip("\ufeff")
    return StructuredImportPreviewOut(data_type=data_type, filename=filename, checksum=hashlib.sha256(normalized.encode()).hexdigest(), parsed_data=parsed)


@router.post("/projects/{project_id}/structured-imports/apply", response_model=StructuredImportApplyOut, status_code=status.HTTP_201_CREATED)
async def apply_structured_import(
    project_id: int,
    user: CurrentUser,
    db: DBSession,
    data_type: StructuredDataType = Form(...),
    batch_key: str | None = Form(default=None),
    file: UploadFile = File(...),
) -> StructuredImportApplyOut:
    filename, content = await _markdown(file)
    try:
        item, counts, idempotent = structured_import_service.apply_import(db, user.id, project_id, data_type, filename, content, batch_key)
    except structured_import_service.StructuredImportError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return StructuredImportApplyOut(item=StructuredImportOut.model_validate(item), applied_counts=counts, idempotent=idempotent)


@router.get("/projects/{project_id}/structured-imports", response_model=list[StructuredImportOut])
def get_structured_imports(project_id: int, user: CurrentUser, db: DBSession) -> list[StructuredImportOut]:
    try:
        items = structured_import_service.list_imports(db, user.id, project_id)
    except structured_import_service.StructuredImportError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return [StructuredImportOut.model_validate(item) for item in items]
