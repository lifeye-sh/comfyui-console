"""AI provider, prompt, generation audit and novel-analysis models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AIProviderConfig(Base, TimestampMixin):
    __tablename__ = "ai_provider_configs"
    __table_args__ = (UniqueConstraint("name", name="uq_ai_provider_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="openai_compatible", nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_hint: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, default=8192, nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class ImageProviderConfig(Base, TimestampMixin):
    """Image generation/edit provider independent from screenplay LLM providers."""
    __tablename__ = "image_provider_configs"
    __table_args__ = (UniqueConstraint("name", name="uq_image_provider_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="gemini_web2api", nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_hint: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    max_concurrency: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class AIPromptTemplate(Base, TimestampMixin):
    __tablename__ = "ai_prompt_templates"
    __table_args__ = (UniqueConstraint("code", "version", name="uq_ai_prompt_code_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    user_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    response_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class AIGenerationRecord(Base, TimestampMixin):
    __tablename__ = "ai_generation_records"
    __table_args__ = (Index("ix_ai_generation_owner_project", "owner_id", "project_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=True)
    job_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("creative_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    provider_config_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ai_provider_configs.id", ondelete="SET NULL"), nullable=True)
    prompt_template_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ai_prompt_templates.id", ondelete="SET NULL"), nullable=True)
    operation: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="running", nullable=False, index=True)
    request_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    response_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class NovelAnalysisVersion(Base, TimestampMixin):
    __tablename__ = "novel_analysis_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "document_id", "version", name="uq_novel_analysis_version"),
        Index("ix_novel_analysis_project_status", "project_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[int] = mapped_column(Integer, ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False)
    generation_record_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ai_generation_records.id", ondelete="SET NULL"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="candidate", nullable=False)
    chapter_start: Mapped[int] = mapped_column(Integer, nullable=False)
    chapter_end: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    validation_errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ScreenplayRevisionCandidate(Base, TimestampMixin):
    """AI 生成的单集剧本候选，确认前绝不覆盖人工草稿。"""
    __tablename__ = "screenplay_revision_candidates"
    __table_args__ = (Index("ix_screenplay_revision_episode_status", "episode_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    episode_id: Mapped[int] = mapped_column(Integer, ForeignKey("drama_episodes.id", ondelete="CASCADE"), nullable=False, index=True)
    generation_record_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ai_generation_records.id", ondelete="SET NULL"), nullable=True)
    base_lock_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False, index=True)
    instruction: Mapped[str] = mapped_column(Text, default="", nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    validation_errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    confirmed_version_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("story_versions.id", ondelete="SET NULL"), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


__all__ = ["AIProviderConfig", "ImageProviderConfig", "AIPromptTemplate", "AIGenerationRecord", "NovelAnalysisVersion", "ScreenplayRevisionCandidate"]
