"""提示词库服务。"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models import Prompt, PromptCategory
from app.schemas.schemas import PromptCreateIn, PromptPatchIn


def seed_default_categories(db: Session) -> None:
    defaults = ["国风", "推文", "玄幻", "动漫", "3D", "科幻", "解压", "搞笑"]
    existing = {c.name for c in db.query(PromptCategory).all()}
    for name in defaults:
        if name in existing:
            continue
        db.add(PromptCategory(name=name))
    db.commit()


def list_categories(db: Session) -> list[PromptCategory]:
    return db.query(PromptCategory).order_by(PromptCategory.sort_order).all()


def create_category(db: Session, name: str) -> PromptCategory:
    c = PromptCategory(name=name)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def list_prompts(
    db: Session,
    keyword: Optional[str] = None,
    category_id: Optional[int] = None,
    owner_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Prompt], int]:
    q = db.query(Prompt)
    if keyword:
        q = q.filter(Prompt.name.contains(keyword) | Prompt.content.contains(keyword))
    if category_id:
        q = q.filter(Prompt.category_id == category_id)
    if owner_id:
        q = q.filter(Prompt.owner_id == owner_id)
    total = q.count()
    items = q.order_by(Prompt.id.desc()).offset(offset).limit(limit).all()
    return items, total


def create_prompt(db: Session, body: PromptCreateIn, owner_id: Optional[int]) -> Prompt:
    p = Prompt(
        owner_id=owner_id,
        name=body.name,
        content=body.content,
        negative_content=body.negative_content or "",
        category_id=body.category_id,
        tags=body.tags or [],
        remark=body.remark or "",
        visibility=body.visibility or "private",
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def patch_prompt(db: Session, p: Prompt, body: PromptPatchIn) -> Prompt:
    for f in ("name", "content", "negative_content", "category_id", "tags", "remark", "visibility"):
        v = getattr(body, f, None)
        if v is not None:
            setattr(p, f, v)
    db.commit()
    db.refresh(p)
    return p


def delete_prompt(db: Session, p: Prompt) -> None:
    db.delete(p)
    db.commit()