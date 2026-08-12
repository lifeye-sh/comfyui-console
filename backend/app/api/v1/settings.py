"""平台设置路由 /api/v1/settings 与选择项管理。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.deps import AdminUser, DBSession
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
def get_select_options(admin: AdminUser, db: DBSession) -> dict:
    """返回所有选择项及其标签。"""
    options = generation_type_service.get_all_select_options(db)
    return {
        key: {
            "label": generation_type_service.SELECT_OPTION_LABELS.get(key, key),
            "options": options.get(key, []),
            "default_value": generation_type_service.get_select_default(db, key),
        }
        for key in generation_type_service.MAINTAINABLE_SELECT_OPTION_KEYS
    }


class SelectOptionItemIn(BaseModel):
    label: str
    value: int | str


class SaveSelectOptionsIn(BaseModel):
    options: list[SelectOptionItemIn]
    default_value: int | str | None = None


@router.put("/select-options/{key}")
def save_select_options(key: str, body: SaveSelectOptionsIn, admin: AdminUser, db: DBSession) -> dict:
    if key not in generation_type_service.DEFAULT_SELECT_OPTIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"未知选择项：{key}")
    options = [{"label": o.label, "value": o.value} for o in body.options]
    try:
        generation_type_service.save_select_options(db, key, options, body.default_value)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return {"ok": True}
