"""提示词库路由 /api/v1/prompts 与 /api/v1/prompt-categories。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, DBSession
from app.models import Prompt, PromptCategory
from app.services import prompt_service
from app.schemas.schemas import PromptCategoryCreateIn, PromptCategoryOut, PromptCreateIn, PromptOut, PromptPatchIn

router = APIRouter(prefix="/prompts", tags=["prompts"])
cat_router = APIRouter(prefix="/prompt-categories", tags=["prompts"])


@cat_router.get("", response_model=list[PromptCategoryOut])
def list_categories(user: CurrentUser, db: DBSession) -> list[PromptCategoryOut]:
    return [PromptCategoryOut.model_validate(c) for c in prompt_service.list_categories(db)]


@cat_router.post("", response_model=PromptCategoryOut, status_code=201)
def create_category(body: PromptCategoryCreateIn, user: CurrentUser, db: DBSession) -> PromptCategoryOut:
    c = prompt_service.create_category(db, body.name)
    return PromptCategoryOut.model_validate(c)


@cat_router.delete("/{cid}", status_code=204, response_model=None)
def delete_category(cid: int, user: CurrentUser, db: DBSession) -> None:
    c = db.get(PromptCategory, cid)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "分类不存在")
    db.delete(c)
    db.commit()


@router.get("", response_model=list[PromptOut])
def list_(
    user: CurrentUser,
    db: DBSession,
    keyword: str | None = None,
    category_id: int | None = None,
) -> list[PromptOut]:
    items, _ = prompt_service.list_prompts(db, keyword, category_id, user.id if user else None)
    return [PromptOut.model_validate(p) for p in items]


@router.post("", response_model=PromptOut, status_code=201)
def create(body: PromptCreateIn, user: CurrentUser, db: DBSession) -> PromptOut:
    p = prompt_service.create_prompt(db, body, user.id)
    return PromptOut.model_validate(p)


@router.patch("/{pid}", response_model=PromptOut)
def patch(pid: int, body: PromptPatchIn, user: CurrentUser, db: DBSession) -> PromptOut:
    p = db.get(Prompt, pid)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "提示词不存在")
    if p.owner_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权修改")
    p = prompt_service.patch_prompt(db, p, body)
    return PromptOut.model_validate(p)


@router.delete("/{pid}", status_code=204, response_model=None)
def delete(pid: int, user: CurrentUser, db: DBSession) -> None:
    p = db.get(Prompt, pid)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "提示词不存在")
    if p.owner_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权删除")
    prompt_service.delete_prompt(db, p)


__all__ = ["router", "cat_router"]
