"""提示词库模型。"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class PromptCategory(Base, TimestampMixin):
    __tablename__ = "prompt_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    prompts: Mapped[List["Prompt"]] = relationship(back_populates="category")


class Prompt(Base, TimestampMixin):
    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    negative_content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("prompt_categories.id"), nullable=True)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    remark: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cover_resource_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    visibility: Mapped[str] = mapped_column(String(16), default="private", nullable=False)

    category: Mapped[Optional["PromptCategory"]] = relationship(back_populates="prompts")


__all__ = ["Prompt", "PromptCategory"]