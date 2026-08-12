"""生产模型：生成类型、工作流、批次、任务、资源。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class GenerationType(Base, TimestampMixin):
    __tablename__ = "generation_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_type: Mapped[str] = mapped_column(String(16), nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    default_workflow_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("workflows.id"), nullable=True)
    param_template: Mapped[Dict] = mapped_column(JSON, default=dict)
    menu_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    default_workflow: Mapped[Optional["Workflow"]] = relationship(foreign_keys=[default_workflow_id])
    batches: Mapped[List["Batch"]] = relationship(back_populates="generation_type")


class Workflow(Base, TimestampMixin):
    __tablename__ = "workflows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    generation_type_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("generation_types.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    media_type: Mapped[str] = mapped_column(String(16), default="image", nullable=False)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    cover_resource_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_version_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)

    versions: Mapped[List["WorkflowVersion"]] = relationship(back_populates="workflow", order_by="WorkflowVersion.version")


class WorkflowVersion(Base, TimestampMixin):
    __tablename__ = "workflow_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workflow_id: Mapped[int] = mapped_column(Integer, ForeignKey("workflows.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    ui_json: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    api_json: Mapped[Dict] = mapped_column(JSON, nullable=False)
    param_schema: Mapped[List] = mapped_column(JSON, default=list)
    output_mapping: Mapped[Dict] = mapped_column(JSON, default=dict)

    workflow: Mapped["Workflow"] = relationship(back_populates="versions")


class Batch(Base, TimestampMixin):
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    generation_type_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("generation_types.id"), nullable=True)
    workflow_version_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("workflow_versions.id"), nullable=True)
    global_params: Mapped[Dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped[Optional["User"]] = relationship(back_populates="batches")
    generation_type: Mapped[Optional["GenerationType"]] = relationship(back_populates="batches")
    tasks: Mapped[List["Task"]] = relationship(back_populates="batch", order_by="Task.row_no")


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(Integer, ForeignKey("batches.id"), nullable=False, index=True)
    row_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    generation_type_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("generation_types.id"), nullable=True)
    workflow_version_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("workflow_versions.id"), nullable=True)
    params: Mapped[Dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    node_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("nodes.id"), nullable=True)
    prompt_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    batch: Mapped["Batch"] = relationship(back_populates="tasks")
    events: Mapped[List["TaskEvent"]] = relationship(back_populates="task", order_by="TaskEvent.created_at")


class TaskEvent(Base):
    __tablename__ = "task_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payload: Mapped[Dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    task: Mapped["Task"] = relationship(back_populates="events")


class Resource(Base, TimestampMixin):
    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    folder_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("resource_folders.id"), nullable=True, index=True)
    media_type: Mapped[str] = mapped_column(String(16), default="image", nullable=False)
    direction: Mapped[str] = mapped_column(String(16), default="output", nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime: Mapped[str] = mapped_column(String(128), default="application/octet-stream", nullable=False)
    size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    thumb_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    visibility: Mapped[str] = mapped_column(String(16), default="private", nullable=False)
    meta: Mapped[Dict] = mapped_column(JSON, default=dict)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ResourceFolder(Base, TimestampMixin):
    __tablename__ = "resource_folders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("resource_folders.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    folder_type: Mapped[str] = mapped_column(String(16), default="normal", nullable=False)
    system_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class TaskResource(Base):
    __tablename__ = "task_resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)
    resource_id: Mapped[int] = mapped_column(Integer, ForeignKey("resources.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), default="input", nullable=False)
    slot_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


__all__ = [
    "GenerationType", "Workflow", "WorkflowVersion", "Batch", "Task",
    "TaskEvent", "Resource", "ResourceFolder", "TaskResource",
]
