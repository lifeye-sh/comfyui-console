"""Structured Markdown imports for short-drama production."""
from __future__ import annotations
from typing import Any
from sqlalchemy import ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class StructuredDramaImport(Base, TimestampMixin):
    """Immutable source text plus the normalized result of one staged import."""
    __tablename__ = "drama_structured_imports"
    __table_args__ = (
        UniqueConstraint("project_id", "data_type", "checksum", name="uq_drama_structured_import_source"),
        Index("ix_drama_structured_import_batch", "project_id", "batch_key", "data_type"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    data_type: Mapped[str] = mapped_column(String(24), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="previewed", nullable=False, index=True)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
