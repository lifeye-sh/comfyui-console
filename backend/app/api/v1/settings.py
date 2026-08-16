"""平台设置路由 /api/v1/settings 与选择项管理。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.deps import AdminUser, CurrentUser, DBSession
from app.models import Setting
from app.services import generation_type_service

router = APIRouter(prefix="/settings", tags=["settings"])

# ---- 通用设置 ----
@router.get("")
def list_settings(admin: AdminUser, db: DBSession) -> dict:
    out = {}
    for s in db.query(Setting).all():
        out[s.key] = s.value
    return out


@router.patch("")
def patch_settings(body: dict, admin: AdminUser, db: DBSession) -> dict:
    for k, v in body.items():
        s = db.get(Setting, k)
        if s:
            s.value = v
        else:
            db.add(Setting(key=k, value=v))
    db.commit()
    return {"ok": True}


# ---- 选择项管理 ----
@router.get("/select-options")
def get_select_options(user: CurrentUser, db: DBSession) -> dict:
    """返回所有选择项及其标签。"""
    options = generation_type_service.get_all_select_options(db)
    return {
        definition["key"]: {
            "label": definition["label"],
            "value_type": definition["value_type"],
            "custom": definition["custom"],
            "options": options.get(definition["key"], []),
            "default_value": generation_type_service.get_select_default(db, definition["key"]),
        }
        for definition in generation_type_service.get_select_option_definitions(db)
    }


class SelectOptionItemIn(BaseModel):
    label: str
    value: int | str


class SaveSelectOptionsIn(BaseModel):
    options: list[SelectOptionItemIn]
    default_value: int | str | None = None


class CreateSelectOptionProjectIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    value_type: str = "string"


@router.post("/select-options", status_code=status.HTTP_201_CREATED)
def create_select_option_project(body: CreateSelectOptionProjectIn, admin: AdminUser, db: DBSession) -> dict:
    try:
        return generation_type_service.create_select_option_project(db, body.label, body.value_type)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.put("/select-options/{key}")
def save_select_options(key: str, body: SaveSelectOptionsIn, admin: AdminUser, db: DBSession) -> dict:
    if not generation_type_service.is_select_option_project(db, key):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"未知选择项：{key}")
    options = [{"label": o.label, "value": o.value} for o in body.options]
    try:
        generation_type_service.save_select_options(db, key, options, body.default_value)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return {"ok": True}


@router.delete("/select-options/{key}")
def delete_select_option_project(key: str, admin: AdminUser, db: DBSession) -> dict:
    try:
        generation_type_service.delete_select_option_project(db, key)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"ok": True}
