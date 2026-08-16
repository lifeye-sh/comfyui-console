"""生成类型路由 /api/v1/generation-types。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.deps import AdminUser, CurrentUser, DBSession
from app.models import GenerationType
from app.services import generation_type_service
from app.schemas.schemas import DefaultWorkflowIn, GenerationTypeOut, GenerationTypePatchIn

router = APIRouter(prefix="/generation-types", tags=["generation-types"])


class MotionTransferSchemeIn(BaseModel):
    id: int
    name: str = Field(min_length=1, max_length=64)
    is_default: bool = False
    params: dict


class MotionTransferSchemesIn(BaseModel):
    schemes: list[MotionTransferSchemeIn]


@router.get("", response_model=list[GenerationTypeOut])
def list_(
    user: CurrentUser,
    db: DBSession,
    media_type: str | None = None,
    enabled: bool | None = None,
) -> list[GenerationTypeOut]:
    items = generation_type_service.list_types(db, media_type, enabled_only=bool(enabled))
    result = []
    for item in items:
        output = GenerationTypeOut.model_validate(item)
        output.can_delete = generation_type_service.can_delete_type(db, item)
        result.append(output)
    return result


@router.get("/menu")
def menu(user: CurrentUser, db: DBSession) -> dict:
    return generation_type_service.menu_tree(db)


@router.get("/motion-transfer/parameter-schemes")
def get_motion_transfer_schemes(user: CurrentUser, db: DBSession) -> list[dict]:
    return generation_type_service.get_motion_transfer_schemes(db)


@router.put("/motion-transfer/parameter-schemes")
def save_motion_transfer_schemes(body: MotionTransferSchemesIn, admin: AdminUser, db: DBSession) -> list[dict]:
    return generation_type_service.save_motion_transfer_schemes(db, [item.model_dump() for item in body.schemes])


@router.patch("/{type_id}", response_model=GenerationTypeOut)
def patch(
    type_id: int,
    body: GenerationTypePatchIn,
    admin: AdminUser,
    db: DBSession,
) -> GenerationTypeOut:
    gt = db.get(GenerationType, type_id)
    if not gt or gt.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "生成类型不存在")
    gt = generation_type_service.patch_type(db, gt, body.param_template, body.enabled, body.menu_order)
    return GenerationTypeOut.model_validate(gt)


@router.patch("/{type_id}/default-workflow", response_model=GenerationTypeOut)
def set_default(type_id: int, body: DefaultWorkflowIn, admin: AdminUser, db: DBSession) -> GenerationTypeOut:
    gt = db.get(GenerationType, type_id)
    if not gt or gt.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "生成类型不存在")
    try:
        gt = generation_type_service.set_default_workflow(db, gt, body.workflow_version_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return GenerationTypeOut.model_validate(gt)
