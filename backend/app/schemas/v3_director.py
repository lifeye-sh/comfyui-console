"""V3 AI 导演前期制作 schemas。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class StableIdentityOut(BaseModel):
    id: int
    project_id: int
    entity_type: str
    stable_key: str
    status: str
    created_from_type: Optional[str] = None
    created_from_id: Optional[int] = None
    retired_at: Optional[datetime] = None
    retired_reason: Optional[str] = None
    created_at: datetime


class StableIdentityAllocateIn(BaseModel):
    entity_type: str
    created_from_type: Optional[str] = None
    created_from_id: Optional[int] = None


class StableIdentityRetireIn(BaseModel):
    reason: str = ""


class StepStateOut(BaseModel):
    step: int
    label: str
    checkpoint: Optional[str] = None
    gate_status: str
    passed_at: Optional[datetime] = None


class WorkflowStateOut(BaseModel):
    project_id: int
    run_id: int
    current_step: int
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    steps: list[StepStateOut]


class SetGateIn(BaseModel):
    gate_status: str
    reason: Optional[str] = None


class AdvanceIn(BaseModel):
    allow_blocked: bool = False


class ApprovalSubmitIn(BaseModel):
    target_type: str
    target_ref: str
    payload: dict[str, Any] = Field(default_factory=dict)
    validation_errors: list = Field(default_factory=list)
    parent_approved_id: Optional[int] = None


class ApprovalDecideIn(BaseModel):
    reason: str = ""


# ============ 第 7 轮：依赖图 / Manifest / 连续性审计 ============


# ---- 依赖图 ----

class DependencyOut(BaseModel):
    id: int
    downstream_type: str
    downstream_ref: str
    upstream_type: str
    upstream_ref: str
    dependency_type: str
    created_at: datetime


class StaleRecordOut(BaseModel):
    id: int
    project_id: int
    asset_type: str
    asset_ref: str
    stale_reason: str
    detail: str
    source_dependency_id: Optional[int] = None
    status: str
    resolution: str
    created_at: datetime


class StaleResolveIn(BaseModel):
    resolution: str = ""


# ---- Manifest ----

class ManifestReferenceOut(BaseModel):
    id: int
    reference_type: str
    reference_key: str
    reference_version_id: Optional[int] = None
    role: str


class ManifestItemOut(BaseModel):
    id: int
    asset_stable_key: str
    asset_type: str
    parent_key: Optional[str] = None
    scenes: list = Field(default_factory=list)
    style_version_id: Optional[int] = None
    palette_version_id: Optional[int] = None
    required_view: str
    prompt: str
    negative_constraints: str
    aspect_ratio: str
    status: str
    notes: str
    references: list[ManifestReferenceOut] = Field(default_factory=list)


class ManifestOut(BaseModel):
    id: int
    project_id: int
    version: int
    parent_version_id: Optional[int] = None
    status: str
    style_bible_id: Optional[int] = None
    notes: str
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    items: list[ManifestItemOut] = Field(default_factory=list)


class BuildManifestIn(BaseModel):
    notes: str = ""


class ApproveManifestIn(BaseModel):
    reason: str = ""


# ---- 审计 ----

class AuditIssueTargetOut(BaseModel):
    id: int
    target_type: str
    target_ref: str
    manifest_item_id: Optional[int] = None


class AuditIssueOut(BaseModel):
    id: int
    dimension: str
    severity: str
    description: str
    status: str
    resolution: str
    waive_reason: Optional[str] = None
    waived_by: Optional[int] = None
    targets: list[AuditIssueTargetOut] = Field(default_factory=list)


class AuditRunOut(BaseModel):
    id: int
    project_id: int
    manifest_version_id: Optional[int] = None
    status: str
    summary: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime
    finished_at: Optional[datetime] = None
    issues: list[AuditIssueOut] = Field(default_factory=list)


class CreateAuditRunIn(BaseModel):
    manifest_version_id: Optional[int] = None


class WaiveIssueIn(BaseModel):
    reason: str


# ---- 检测缺口 ----

class DetectedGapOut(BaseModel):
    id: int
    gap_type: str
    description: str
    suggested_fix: str
    affected_refs: list = Field(default_factory=list)
    status: str
    created_at: datetime


# ============ 第 8 轮：Manifest 编译 / 生产链路 ============


class ManifestCompilePreviewIn(BaseModel):
    generation_type_id: int
    workflow_version_id: Optional[int] = None
    item_ids: list[int] = Field(default_factory=list)
    parameter_overrides: dict[str, Any] = Field(default_factory=dict)
    item_parameter_overrides: dict[int, dict[str, Any]] = Field(default_factory=dict)


class ManifestCompileCreateIn(ManifestCompilePreviewIn):
    idempotency_key: str = Field(min_length=1, max_length=80)
    submit: bool = True


class ManifestTaskLinkOut(BaseModel):
    id: int
    manifest_item_id: int
    asset_stable_key: Optional[str] = None
    task_id: int
    task_status: Optional[str] = None
    task_error: Optional[str] = None
    output_resource_id: Optional[int] = None
    take_id: Optional[int] = None
    generation_type_id: Optional[int] = None
    workflow_version_id: Optional[int] = None
    link_status: str
    sync_error: str


class ManifestRefreshStatusOut(BaseModel):
    manifest_id: int
    changed_items: int
    summary: dict[str, Any] = Field(default_factory=dict)


# ============ 第 9 轮：AI 导演对话 / 建议 / 提案 ============


class ConversationCreateIn(BaseModel):
    title: str = "新对话"


class ChatMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    revision_hash: str
    proposal_id: Optional[int] = None
    ai_meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ConversationOut(BaseModel):
    id: int
    project_id: int
    title: str
    status: str
    created_at: datetime
    messages: list[MessageOut] = Field(default_factory=list)


class ProposalCreateIn(BaseModel):
    action_type: str
    target_type: str
    target_ref: str
    title: str = ""
    rationale: str = ""
    changes: list = Field(default_factory=list)
    impact_refs: list = Field(default_factory=list)


class ProposalOut(BaseModel):
    id: int
    action_type: str
    action_desc: str
    target_type: str
    target_ref: str
    target_lock_version: int
    base_revision_hash: str
    revision_current: bool
    title: str
    rationale: str
    changes: list = Field(default_factory=list)
    impact_refs: list = Field(default_factory=list)
    status: str
    applied_at: Optional[datetime] = None
    apply_error: str
    dismissed_reason: str
    created_at: datetime


class ProposalDismissIn(BaseModel):
    reason: str = ""


class GuidanceOut(BaseModel):
    suggestions: list = Field(default_factory=list)
    revision_hash: str = ""
    ai_meta: dict[str, Any] = Field(default_factory=dict)
