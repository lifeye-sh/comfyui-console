"""提示词库模型与分类 Pydantic 模型。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PromptCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    sort_order: int


class PromptCategoryCreateIn(BaseModel):
    name: str


class PromptCreateIn(BaseModel):
    name: str
    content: str
    negative_content: str = ""
    category_id: Optional[int] = None
    tags: list[str] = Field(default_factory=list)
    remark: str = ""
    visibility: str = "private"


class PromptPatchIn(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    negative_content: Optional[str] = None
    category_id: Optional[int] = None
    tags: Optional[list[str]] = None
    remark: Optional[str] = None
    visibility: Optional[str] = None


class PromptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    owner_id: Optional[int]
    name: str
    content: str
    negative_content: str
    category_id: Optional[int]
    tags: list[str]
    remark: str
    visibility: str
