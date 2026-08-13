from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, status

from app.core.deps import AdminUser, CurrentUser, DBSession
from app.models import GenerationType, GenerationTypeConfigVersion
from app.schemas.generation_type_config import (
    ConfigDiffOut,
    ConfigRollbackIn,
    ConfigValidationOut,
    GenerationTypeConfigSaveIn,
    GenerationTypeConfigVersionOut,
)
from app.services import audit_service, generation_type_config_service as service

router = APIRouter(prefix="/generation-types", tags=["v2-generation-type-configs"])


def _type_or_404(db: DBSession, type_id: int) -> GenerationType:
    generation_type = db.get(GenerationType, type_id)
    if not generation_type:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "生成类型不存在")
    return generation_type


@router.get("/{type_id}/config")
def get_active_config(type_id: int, user: CurrentUser, db: DBSession) -> dict:
    generation_type = _type_or_404(db, type_id)
    version = db.get(GenerationTypeConfigVersion, generation_type.published_config_version_id) \
        if generation_type.published_config_version_id else None
    return {
        "generation_type_id": type_id,
        "published_version_id": version.id if version else None,
        "config": version.config if version else service.build_default_config(db, generation_type),
    }


@router.get("/{type_id}/config/draft", response_model=GenerationTypeConfigVersionOut)
def get_draft(type_id: int, admin: AdminUser, db: DBSession) -> GenerationTypeConfigVersionOut:
    draft = service.get_or_create_draft(db, _type_or_404(db, type_id), admin.id)
    return GenerationTypeConfigVersionOut.model_validate(draft)


@router.put("/{type_id}/config/draft", response_model=GenerationTypeConfigVersionOut)
def save_draft(
    type_id: int, body: GenerationTypeConfigSaveIn, admin: AdminUser, db: DBSession
) -> GenerationTypeConfigVersionOut:
    draft = service.save_draft(db, _type_or_404(db, type_id), body.config, admin.id)
    audit_service.log(db, admin.id, "generation_type.config.save_draft", "generation_type", type_id,
                      json.dumps({"version_id": draft.id}, ensure_ascii=False))
    return GenerationTypeConfigVersionOut.model_validate(draft)


@router.post("/{type_id}/config/validate", response_model=ConfigValidationOut)
def validate_config(
    type_id: int, body: GenerationTypeConfigSaveIn, admin: AdminUser, db: DBSession
) -> ConfigValidationOut:
    return ConfigValidationOut(**service.validate_config(db, _type_or_404(db, type_id), body.config))


@router.post("/{type_id}/config/publish", response_model=GenerationTypeConfigVersionOut)
def publish(type_id: int, admin: AdminUser, db: DBSession) -> GenerationTypeConfigVersionOut:
    generation_type = _type_or_404(db, type_id)
    draft = service.get_or_create_draft(db, generation_type, admin.id)
    try:
        published = service.publish_draft(db, generation_type, draft, admin.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    audit_service.log(db, admin.id, "generation_type.config.publish", "generation_type", type_id,
                      json.dumps({"version_id": published.id}, ensure_ascii=False))
    return GenerationTypeConfigVersionOut.model_validate(published)


@router.get("/{type_id}/config/versions", response_model=list[GenerationTypeConfigVersionOut])
def versions(type_id: int, admin: AdminUser, db: DBSession) -> list[GenerationTypeConfigVersionOut]:
    _type_or_404(db, type_id)
    return [GenerationTypeConfigVersionOut.model_validate(item) for item in service.list_versions(db, type_id)]


@router.get("/{type_id}/config/versions/{version_id}", response_model=GenerationTypeConfigVersionOut)
def version(type_id: int, version_id: int, admin: AdminUser, db: DBSession) -> GenerationTypeConfigVersionOut:
    item = service.get_version(db, type_id, version_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "配置版本不存在")
    return GenerationTypeConfigVersionOut.model_validate(item)


@router.get("/{type_id}/config/diff", response_model=ConfigDiffOut)
def diff(type_id: int, from_version_id: int, to_version_id: int, admin: AdminUser, db: DBSession) -> ConfigDiffOut:
    first = service.get_version(db, type_id, from_version_id)
    second = service.get_version(db, type_id, to_version_id)
    if not first or not second:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "配置版本不存在")
    return ConfigDiffOut(
        from_version_id=first.id,
        to_version_id=second.id,
        changes=service.diff_versions(first, second),
    )


@router.post("/{type_id}/config/rollback", response_model=GenerationTypeConfigVersionOut)
def rollback(
    type_id: int, body: ConfigRollbackIn, admin: AdminUser, db: DBSession
) -> GenerationTypeConfigVersionOut:
    generation_type = _type_or_404(db, type_id)
    source = service.get_version(db, type_id, body.source_version_id)
    if not source:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "配置版本不存在")
    try:
        rolled_back = service.rollback(db, generation_type, source, admin.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    audit_service.log(db, admin.id, "generation_type.config.rollback", "generation_type", type_id,
                      json.dumps({"source_version_id": source.id, "version_id": rolled_back.id}, ensure_ascii=False))
    return GenerationTypeConfigVersionOut.model_validate(rolled_back)


@router.post("/{type_id}/config/deactivate")
def deactivate(type_id: int, admin: AdminUser, db: DBSession) -> dict:
    generation_type = _type_or_404(db, type_id)
    generation_type.enabled = False
    db.commit()
    audit_service.log(db, admin.id, "generation_type.config.deactivate", "generation_type", type_id)
    return {"ok": True, "enabled": False}
