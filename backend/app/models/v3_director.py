"""V3 AI 导演前期制作领域模型：稳定键、工作流、审批（第 1 轮）+ 故事级台账（第 2 轮）。

契约见 docs/v3-director-rfc.md。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


# ============ 第 1 轮：稳定键 / 工作流 / 审批 ============

class V3StableIdentity(Base, TimestampMixin):
    """稳定业务键。键在同一 (project_id, entity_type) 内唯一，退役后不复用。"""

    __tablename__ = "v3_stable_identities"
    __table_args__ = (
        UniqueConstraint("project_id", "entity_type", "stable_key", name="uq_v3_identity_project_type_key"),
        Index("ix_v3_identity_project_type", "project_id", "entity_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    stable_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False, index=True)
    created_from_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_from_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    retired_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    retired_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class V3DirectorWorkflowRun(Base, TimestampMixin):
    """每个项目一条导演前期工作流运行；current_step 是该流程唯一事实源。"""

    __tablename__ = "v3_director_workflow_runs"
    __table_args__ = (UniqueConstraint("project_id", name="uq_v3_workflow_run_project"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False)
    current_step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    steps: Mapped[list["V3DirectorStepState"]] = relationship(
        back_populates="run", order_by="V3DirectorStepState.step", cascade="all, delete-orphan"
    )


class V3DirectorStepState(Base, TimestampMixin):
    """单个步骤的门禁状态。"""

    __tablename__ = "v3_director_step_states"
    __table_args__ = (UniqueConstraint("workflow_run_id", "step", name="uq_v3_step_run_step"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workflow_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("v3_director_workflow_runs.id"), nullable=False, index=True
    )
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    gate_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    passed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    waive_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    run: Mapped["V3DirectorWorkflowRun"] = relationship(back_populates="steps")


class V3ApprovalDecision(Base, TimestampMixin):
    """统一审批决策记录：候选提交、批准、拒绝、豁免。"""

    __tablename__ = "v3_approval_decisions"
    __table_args__ = (Index("ix_v3_approval_project_target", "project_id", "target_type", "target_ref"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    owner_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    target_type: Mapped[str] = mapped_column(String(48), nullable=False)
    target_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="candidate", nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    validation_errors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    parent_approved_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    decided_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    decision_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lock_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# ============ 第 2 轮：故事级台账 / 情感曲线 / Checkpoint A 决策 ============
class V3ScriptLedgerVersion(Base, TimestampMixin):
    """故事级台账版本：绑定源文档与分析版本，包含节拍表和情感曲线数据源。"""

    __tablename__ = "v3_script_ledger_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_v3_ledger_project_version"),
        Index("ix_v3_ledger_project_status", "project_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    document_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("source_documents.id"), nullable=True)
    analysis_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("novel_analysis_versions.id"), nullable=True)
    generation_record_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ai_generation_records.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # draft / candidate / approved / rejected / stale / retired
    status: Mapped[str] = mapped_column(String(16), default="candidate", nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 合并的结构化档案：synopsis/core_conflict/characters/locations/facts 等（继承自分析）
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    validation_errors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    approved_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    lock_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    beats: Mapped[list["V3StoryBeat"]] = relationship(
        back_populates="ledger", order_by="V3StoryBeat.order", cascade="all, delete-orphan"
    )


class V3StoryBeat(Base, TimestampMixin):
    """故事节拍：情感曲线的数据事实源。

    校验规则（RFC §5.1）：
    - intensity 范围 0-10；valence 范围 -5~+5
    - evidence_type 只能是 explicit/inferred/assumed
    - assumed 必须带 confidence (0-1)
    - source_locator 必填（章节/段落定位）
    """

    __tablename__ = "v3_story_beats"
    __table_args__ = (
        UniqueConstraint("ledger_id", "stable_key", name="uq_v3_beat_ledger_key"),
        Index("ix_v3_beat_ledger_order", "ledger_id", "order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ledger_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("v3_script_ledger_versions.id"), nullable=False, index=True
    )
    stable_key: Mapped[str] = mapped_column(String(64), nullable=False)  # BT-001
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    event: Mapped[str] = mapped_column(Text, nullable=False)
    goal: Mapped[str] = mapped_column(Text, default="", nullable=False)
    conflict: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reversal: Mapped[str] = mapped_column(Text, default="", nullable=False)
    outcome: Mapped[str] = mapped_column(Text, default="", nullable=False)
    causal_dependency: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # 前序 BT 键
    characters: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # 参与角色名列表
    emotion_intensity: Mapped[float] = mapped_column(Float, nullable=False)   # 0-10
    emotion_valence: Mapped[float] = mapped_column(Float, nullable=False)     # -5 ~ +5
    dominant_emotion: Mapped[str] = mapped_column(String(48), default="", nullable=False)
    narrative_function: Mapped[str] = mapped_column(String(96), default="", nullable=False)
    # explicit / inferred / assumed
    evidence_type: Mapped[str] = mapped_column(String(16), default="inferred", nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # assumed 时必填 0-1
    source_locator: Mapped[str] = mapped_column(Text, default="", nullable=False)  # 章节/段落定位

    ledger: Mapped["V3ScriptLedgerVersion"] = relationship(back_populates="beats")


class V3LedgerDecision(Base, TimestampMixin):
    """Checkpoint A 决策集：源材料矛盾的最小决策记录。"""

    __tablename__ = "v3_ledger_decisions"
    __table_args__ = (
        Index("ix_v3_decision_project_status", "project_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    ledger_version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("v3_script_ledger_versions.id"), nullable=False
    )
    owner_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # 候选选项
    chosen: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False, index=True)  # open/resolved/waived
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)


# ============ 第 3 轮：场景级台账 / 角色与道具状态 / 连续性事实 / 稳定键对齐 ============

class V3LedgerScene(Base, TimestampMixin):
    """场景级台账：绑定 StoryVersion，通过 scene_ref 映射当前 Scene，稳定键不依赖 Scene.id。

    story_version_id 记录创建时的故事版本；替换 StoryVersion 后按匹配沿用稳定键。
    """

    __tablename__ = "v3_ledger_scenes"
    __table_args__ = (
        UniqueConstraint("project_id", "stable_key", name="uq_v3_ledger_scene_key"),
        Index("ix_v3_ledger_scene_project_sv", "project_id", "story_version_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    story_version_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("story_versions.id"), nullable=True)
    ledger_version_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("v3_script_ledger_versions.id"), nullable=True
    )
    stable_key: Mapped[str] = mapped_column(String(64), nullable=False)  # SC-001
    # 当前映射的 Scene.id（可空：Scene 重建后由对齐流程重连）
    scene_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("drama_scenes.id", ondelete="SET NULL"), nullable=True)
    episode_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    heading: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    location_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    time_of_day: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    interior_exterior: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    purpose: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # explicit/inferred/assumed
    evidence_type: Mapped[str] = mapped_column(String(16), default="inferred", nullable=False)
    source_locator: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False, index=True)
    alignment_status: Mapped[str] = mapped_column(String(16), default="aligned", nullable=False)  # aligned/pending/retired

    appearances: Mapped[list["V3SceneCharacterAppearance"]] = relationship(
        back_populates="ledger_scene", cascade="all, delete-orphan"
    )
    prop_states: Mapped[list["V3ScenePropState"]] = relationship(
        back_populates="ledger_scene", cascade="all, delete-orphan"
    )


class V3SceneCharacterAppearance(Base, TimestampMixin):
    """角色在场景中的状态：服装/发妆/伤损/污渍/情绪。按 (scene, character) 可追溯变化。"""

    __tablename__ = "v3_scene_character_appearances"
    __table_args__ = (
        UniqueConstraint("ledger_scene_id", "character_stable_key", name="uq_v3_app_scene_char"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ledger_scene_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("v3_ledger_scenes.id"), nullable=False, index=True
    )
    character_stable_key: Mapped[str] = mapped_column(String(64), nullable=False)  # CH-001
    character_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    costume: Mapped[str] = mapped_column(Text, default="", nullable=False)
    hair_makeup: Mapped[str] = mapped_column(Text, default="", nullable=False)
    injuries_dirt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    emotional_state: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    change_from_previous: Mapped[str] = mapped_column(Text, default="", nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(16), default="inferred", nullable=False)
    source_locator: Mapped[str] = mapped_column(Text, default="", nullable=False)

    ledger_scene: Mapped["V3LedgerScene"] = relationship(back_populates="appearances")


class V3ScenePropState(Base, TimestampMixin):
    """道具在场景中的状态：所有者/位置/状态变化。"""

    __tablename__ = "v3_scene_prop_states"
    __table_args__ = (
        UniqueConstraint("ledger_scene_id", "prop_stable_key", name="uq_v3_propstate_scene_prop"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ledger_scene_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("v3_ledger_scenes.id"), nullable=False, index=True
    )
    prop_stable_key: Mapped[str] = mapped_column(String(64), nullable=False)  # PR-001
    prop_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    owner_character_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    location_in_scene: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    condition: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    interaction: Mapped[str] = mapped_column(Text, default="", nullable=False)
    state_change: Mapped[str] = mapped_column(Text, default="", nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(16), default="inferred", nullable=False)
    source_locator: Mapped[str] = mapped_column(Text, default="", nullable=False)

    ledger_scene: Mapped["V3LedgerScene"] = relationship(back_populates="prop_states")


class V3ContinuityFact(Base, TimestampMixin):
    """连续性事实：跨场景需要保持的事实（如"左眼伤疤从第 3 场起存在"）。

    severity：info/risk/blocker；resolved 时记录 resolution。
    """

    __tablename__ = "v3_continuity_facts"
    __table_args__ = (
        Index("ix_v3_cf_project_severity", "project_id", "severity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    story_version_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("story_versions.id"), nullable=True)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)  # character/prop/location/scene/timeline
    subject_key: Mapped[str] = mapped_column(String(64), nullable=False)  # 稳定键
    fact: Mapped[str] = mapped_column(Text, nullable=False)
    from_scene_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    to_scene_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    evidence_type: Mapped[str] = mapped_column(String(16), default="inferred", nullable=False)
    source_locator: Mapped[str] = mapped_column(Text, default="", nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False, index=True)
    resolution: Mapped[str] = mapped_column(Text, default="", nullable=False)
    resolved_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)


# ============ 第 6 轮：空间拓扑 / 内景平面图 / 关键视图 ============

class V3SpatialPlanVersion(Base, TimestampMixin):
    """空间结构版本：外景拓扑或内景平面图。结构版本先于视图版本创建。"""

    __tablename__ = "v3_spatial_plan_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "location_stable_key", "version", name="uq_v3_spatial_key_ver"),
        Index("ix_v3_spatial_project_status", "project_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    location_stable_key: Mapped[str] = mapped_column(String(64), nullable=False)  # LOC-001
    location_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("drama_locations.id", ondelete="SET NULL"), nullable=True
    )
    plan_kind: Mapped[str] = mapped_column(String(16), default="exterior", nullable=False)  # exterior/interior
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="candidate", nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    scale: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    topology: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    floor_plan: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    validation_errors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    approved_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    lock_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class V3LocationViewVersion(Base, TimestampMixin):
    """地点关键视图版本：必须引用 SpatialPlanVersion（外键强制）。"""

    __tablename__ = "v3_location_view_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "stable_key", "version", name="uq_v3_locview_key_ver"),
        Index("ix_v3_locview_project_status", "project_id", "status"),
        Index("ix_v3_locview_plan", "spatial_plan_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    spatial_plan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("v3_spatial_plan_versions.id"), nullable=False
    )
    stable_key: Mapped[str] = mapped_column(String(64), nullable=False)  # LOC-001-V01
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="candidate", nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    view_angle: Mapped[str] = mapped_column(String(96), default="", nullable=False)
    resource_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    validation_errors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    approved_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    lock_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# ============ 第 5 轮：角色/道具锚点 / Checkpoint C ============

class V3CharacterAnchorVersion(Base, TimestampMixin):
    """角色身份锚点版本：不可变身份特征与可控变量严格分离。

    - identity_anchor：不可变（面部比例/眼距/鼻颌/年龄范围/体型/肤色/特征标记/基线发际线）
    - controllable_vars：可控（表情/姿势/服装/造型/伤损/光照）
    - drift_prohibition：禁止漂移规则
    - Checkpoint C：逐实体审批，批准后才能生成变体；不允许全局自动通过
    """

    __tablename__ = "v3_character_anchor_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "stable_key", "version", name="uq_v3_char_anchor_key_ver"),
        Index("ix_v3_char_anchor_project_status", "project_id", "status"),
Index("ix_v3_char_anchor_stable_key", "stable_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    stable_key: Mapped[str] = mapped_column(String(64), nullable=False)  # CH-001
    character_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("drama_characters.id", ondelete="SET NULL"), nullable=True
    )
    style_bible_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("v3_style_bible_versions.id"), nullable=True
    )
    generation_record_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ai_generation_records.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="candidate", nullable=False, index=True)
    # 主角优先级：protagonist > supporting > extra；配角生成不能绕过主角依赖
    priority: Mapped[str] = mapped_column(String(16), default="supporting", nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    # 不可变身份锚点 JSON：face_ratios, eye_spacing, nose_bridge, age_range, body_type,
    # skin_tone, feature_marks, baseline_hairline
    identity_anchor: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    # 可控变量：expression, pose, costume, styling, injuries, lighting
    controllable_vars: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    drift_prohibition: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # 禁止漂移规则列表
    expression_sheet: Mapped[list] = mapped_column(JSON, default=list, nullable=False)   # 表情表变体描述
    # 中性正/侧/背三视图资源（批准后指向生成的图片资源）
    front_resource_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    side_resource_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    back_resource_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    validation_errors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    approved_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    lock_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class V3CharacterStateVersion(Base, TimestampMixin):
    """角色状态版本：服装/年龄/发妆/伤损/情绪/灯光状态。变体必须引用已批准锚点。"""

    __tablename__ = "v3_character_state_versions"
    __table_args__ = (
        Index("ix_v3_char_state_project_key", "project_id", "character_stable_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    character_stable_key: Mapped[str] = mapped_column(String(64), nullable=False)  # CH-001
    anchor_version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("v3_character_anchor_versions.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), default="", nullable=False)  # 如"第3集-雨夜-负伤"
    scene_stable_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # 适用场景
    age_state: Mapped[str] = mapped_column(String(96), default="", nullable=False)
    costume: Mapped[str] = mapped_column(Text, default="", nullable=False)
    hair_makeup: Mapped[str] = mapped_column(Text, default="", nullable=False)
    injuries_dirt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    emotional_state: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    lighting_state: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    carried_props: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # PR 键列表
    status: Mapped[str] = mapped_column(String(16), default="candidate", nullable=False, index=True)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class V3PropAnchorVersion(Base, TimestampMixin):
    """道具锚点版本：尺寸/材质/磨损/所有者/状态变化。"""

    __tablename__ = "v3_prop_anchor_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "stable_key", "version", name="uq_v3_prop_anchor_key_ver"),
        Index("ix_v3_prop_anchor_project_status", "project_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    stable_key: Mapped[str] = mapped_column(String(64), nullable=False)  # PR-001
    prop_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("drama_props.id", ondelete="SET NULL"), nullable=True
    )
    style_bible_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("v3_style_bible_versions.id"), nullable=True
    )
    generation_record_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ai_generation_records.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="candidate", nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    # 按复现率/因果性/交互性/特写重要性排序
    priority_rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    size: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    material: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    wear_condition: Mapped[str] = mapped_column(Text, default="", nullable=False)
    owner_character_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    state_changes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # [{scene_key, change}]
    drift_prohibition: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    hero_shot_resource_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    validation_errors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    approved_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    lock_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# ============ 第 4 轮：风格圣经 / 色卡 / Checkpoint B ============

class V3StyleBibleVersion(Base, TimestampMixin):
    """风格圣经版本：多维度系统化视觉风格定义，版本化、不原地修改。

    palette_version_id 关联的色卡版本通过真实外键连接。
    status: draft/candidate/approved/rejected/stale/retired
    """

    __tablename__ = "v3_style_bible_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_v3_style_project_version"),
        Index("ix_v3_style_project_status", "project_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    palette_version_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("v3_palette_versions.id", use_alter=True), nullable=True
    )
    generation_record_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ai_generation_records.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="candidate", nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    # 一句话视觉论点
    visual_thesis: Mapped[str] = mapped_column(Text, default="", nullable=False)
    era: Mapped[str] = mapped_column(String(128), default="", nullable=False)              # 时代/地理/季节
    realism: Mapped[str] = mapped_column(String(96), default="", nullable=False)           # 写实度/制作价值
    composition: Mapped[str] = mapped_column(Text, default="", nullable=False)             # 构图原则
    aspect_ratio: Mapped[str] = mapped_column(String(16), default="9:16", nullable=False)
    lens_language: Mapped[str] = mapped_column(Text, default="", nullable=False)           # 镜头范围/景深/机高/运动
    lighting: Mapped[str] = mapped_column(Text, default="", nullable=False)                # 主光/辅光/轮廓光/对比/曝光
    texture_material: Mapped[str] = mapped_column(Text, default="", nullable=False)        # 质感/材质/服装逻辑/美术规则
    sound_world: Mapped[str] = mapped_column(Text, default="", nullable=False)             # 对白语域/环境音/BGM
    non_negotiables: Mapped[list] = mapped_column(JSON, default=list, nullable=False)      # 不可妥协项/禁止漂移
    reference_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)        # 参考素材资源 ID
    validation_errors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    approved_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    lock_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    palettes: Mapped[list["V3PaletteVersion"]] = relationship(
        foreign_keys="V3PaletteVersion.style_bible_id", order_by="V3PaletteVersion.id"
    )


class V3PaletteVersion(Base, TimestampMixin):
    """色卡版本：主色/辅色/强调色/中性色/肤色保护/禁用色 + 室内外与时段变体。

    与 StyleBibleVersion 通过 style_bible_id 外键关联。
    """

    __tablename__ = "v3_palette_versions"
    __table_args__ = (
        Index("ix_v3_palette_project", "project_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    style_bible_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("v3_style_bible_versions.id", ondelete="SET NULL"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(96), default="", nullable=False)              # 如"室内-夜"
    scope: Mapped[str] = mapped_column(String(16), default="general", nullable=False)      # general/interior/exterior
    time_variant: Mapped[str] = mapped_column(String(32), default="", nullable=False)      # day/night/dawn/dusk
    primary_color: Mapped[str] = mapped_column(String(16), default="", nullable=False)     # hex
    secondary_color: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    accent_color: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    neutral_color: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    skin_tone_protection: Mapped[str] = mapped_column(String(255), default="", nullable=False)  # 肤色保护区间说明
    forbidden_colors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)     # 禁用色 hex 列表
    exposure_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)          # 曝光/对比说明
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


# ============ 第 7 轮：依赖图 / Manifest / 连续性审计 ============

class V3ArtifactDependency(Base, TimestampMixin):
    """资产依赖边：上游变更时传递生成 StaleRecord。确定性规则建立。"""

    __tablename__ = "v3_artifact_dependencies"
    __table_args__ = (
        Index("ix_v3_dep_project", "project_id"),
        Index("ix_v3_dep_upstream", "upstream_type", "upstream_ref"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    downstream_type: Mapped[str] = mapped_column(String(48), nullable=False)
    downstream_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    upstream_type: Mapped[str] = mapped_column(String(48), nullable=False)
    upstream_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    dependency_type: Mapped[str] = mapped_column(String(32), nullable=False)


class V3StaleRecord(Base, TimestampMixin):
    """过期记录：上游变更产生的下游过期标记。"""

    __tablename__ = "v3_stale_records"
    __table_args__ = (Index("ix_v3_stale_project_status", "project_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(48), nullable=False)
    asset_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    stale_reason: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_dependency_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False, index=True)
    resolved_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    resolution: Mapped[str] = mapped_column(Text, default="", nullable=False)


class V3DetectedGap(Base, TimestampMixin):
    """检测到的缺失项：缺定义/不完整/不一致。"""

    __tablename__ = "v3_detected_gaps"
    __table_args__ = (Index("ix_v3_gap_project_status", "project_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    gap_type: Mapped[str] = mapped_column(String(48), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_fix: Mapped[str] = mapped_column(Text, default="", nullable=False)
    affected_refs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False, index=True)


class V3GenerationManifest(Base, TimestampMixin):
    """生成清单版本。已批准 Manifest 不可原地修改。"""

    __tablename__ = "v3_generation_manifests"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_v3_manifest_project_version"),
        Index("ix_v3_manifest_project_status", "project_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False, index=True)
    style_bible_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("v3_style_bible_versions.id"), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    approved_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    items: Mapped[list["V3ManifestItem"]] = relationship(
        back_populates="manifest", order_by="V3ManifestItem.id", cascade="all, delete-orphan"
    )


class V3ManifestItem(Base, TimestampMixin):
    """清单项：每资产/镜头一行，引用真实版本外键和稳定键。"""

    __tablename__ = "v3_manifest_items"
    __table_args__ = (
        Index("ix_v3_mi_manifest_status", "manifest_id", "status"),
        Index("ix_v3_mi_project_key", "project_id", "asset_stable_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    manifest_id: Mapped[int] = mapped_column(Integer, ForeignKey("v3_generation_manifests.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    asset_stable_key: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    parent_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    scenes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    style_version_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("v3_style_bible_versions.id"), nullable=True)
    palette_version_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("v3_palette_versions.id"), nullable=True)
    reference_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    required_view: Mapped[str] = mapped_column(String(48), default="", nullable=False)
    prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    negative_constraints: Mapped[str] = mapped_column(Text, default="", nullable=False)
    aspect_ratio: Mapped[str] = mapped_column(String(16), default="9:16", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="planned", nullable=False, index=True)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    manifest: Mapped["V3GenerationManifest"] = relationship(back_populates="items")

    references: Mapped[list["V3ManifestReference"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="V3ManifestReference.id"
    )


class V3AuditRun(Base, TimestampMixin):
    """连续性审计运行：9 维覆盖。"""

    __tablename__ = "v3_audit_runs"
    __table_args__ = (Index("ix_v3_audit_project", "project_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    manifest_version_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("v3_generation_manifests.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running", nullable=False, index=True)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    issues: Mapped[list["V3AuditIssue"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class V3AuditIssue(Base, TimestampMixin):
    """审计问题：blocker/conflict/risk/optimization 分级。waive 带审批人和原因。"""

    __tablename__ = "v3_audit_issues"
    __table_args__ = (Index("ix_v3_issue_run_severity", "run_id", "severity"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("v3_audit_runs.id"), nullable=False, index=True)
    dimension: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    affected_assets: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    resolution: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False, index=True)
    waived_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    waive_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    run: Mapped["V3AuditRun"] = relationship(back_populates="issues")

    targets: Mapped[list["V3AuditIssueTarget"]] = relationship(
        back_populates="issue", cascade="all, delete-orphan", order_by="V3AuditIssueTarget.id"
    )


class V3ManifestReference(Base, TimestampMixin):
    """清单项引用表：ManifestItem 与 anchor/spatial/palette/resource 的结构化关联。

    替代 V3ManifestItem.reference_ids 的 JSON 数组方案，提供可查询的关联模型。
    reference_type: character_anchor / prop_anchor / location_view / spatial_plan / palette / resource
    """

    __tablename__ = "v3_manifest_references"
    __table_args__ = (
        UniqueConstraint("manifest_item_id", "reference_type", "reference_key", name="uq_v3_mref_item_type_key"),
        Index("ix_v3_mref_item", "manifest_item_id"),
        Index("ix_v3_mref_type_key", "reference_type", "reference_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    manifest_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("v3_manifest_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reference_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reference_key: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_version_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    role: Mapped[str] = mapped_column(String(32), default="primary", nullable=False)

    item: Mapped["V3ManifestItem"] = relationship(back_populates="references")


class V3AuditIssueTarget(Base, TimestampMixin):
    """审计问题目标表：AuditIssue 与受影响实体/ManifestItem 的结构化关联。

    替代 V3AuditIssue.affected_assets 的 JSON 数组方案，提供可查询的关联模型。
    target_type: manifest_item / character / prop / scene / location / shot
    """

    __tablename__ = "v3_audit_issue_targets"
    __table_args__ = (
        UniqueConstraint("audit_issue_id", "target_type", "target_ref", name="uq_v3_atgt_issue_type_ref"),
        Index("ix_v3_atgt_issue", "audit_issue_id"),
        Index("ix_v3_atgt_type_ref", "target_type", "target_ref"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    audit_issue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("v3_audit_issues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_item_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("v3_manifest_items.id", ondelete="SET NULL"), nullable=True
    )

    issue: Mapped["V3AuditIssue"] = relationship(back_populates="targets")


class V3ManifestItemTaskLink(Base, TimestampMixin):
    """ManifestItem 与生产任务关联：编译产物回写链路。

    ManifestItem → (compile) → Task → (reconcile) → Take → 回写 ManifestItem.status。
    link_status: linked / collecting / synced / failed
    """

    __tablename__ = "v3_manifest_item_task_links"
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key", name="uq_v3_mitl_owner_idem"),
        Index("ix_v3_mitl_item", "manifest_item_id"),
        Index("ix_v3_mitl_task", "task_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    manifest_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("v3_manifest_items.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False
    )
    # 资产级生成（角色/道具/地点）无 Shot，输出直接关联 Resource；
    # 仅当 ManifestItem 映射到具体 Shot 时才回写 take_id。
    output_resource_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("resources.id", ondelete="SET NULL"), nullable=True
    )
    take_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("drama_takes.id", ondelete="SET NULL"), nullable=True
    )
    generation_type_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    workflow_version_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    link_status: Mapped[str] = mapped_column(String(16), default="linked", nullable=False, index=True)
    sync_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)


# ============ 第 9 轮：AI 导演对话 / Context / ActionProposal ============

class V3ContextSnapshot(Base, TimestampMixin):
    """上下文快照：按用途构建的项目上下文 + token 预算 + revision hash + 截断记录。

    revision_hash 用于 revision guard：AI 结果只对生成它的 revision 有效。
    """

    __tablename__ = "v3_context_snapshots"
    __table_args__ = (
        Index("ix_v3_ctx_project_purpose", "project_id", "purpose"),
        Index("ix_v3_ctx_revision", "revision_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)  # guidance/chat/proposal/audit
    revision_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    token_budget: Mapped[int] = mapped_column(Integer, default=4000, nullable=False)
    token_estimated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    truncation_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    superseded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)


class V3DirectorConversation(Base, TimestampMixin):
    """导演对话会话：每会话绑定项目和用途，消息按序追加。"""

    __tablename__ = "v3_director_conversations"
    __table_args__ = (
        Index("ix_v3_conv_project_owner", "project_id", "owner_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), default="新对话", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)  # active/closed
    context_purpose: Mapped[str] = mapped_column(String(32), default="chat", nullable=False)

    messages: Mapped[list["V3DirectorMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="V3DirectorMessage.id"
    )


class V3DirectorMessage(Base, TimestampMixin):
    """导演对话消息：记录来源 context revision 和关联 proposal，可追溯。"""

    __tablename__ = "v3_director_messages"
    __table_args__ = (
        Index("ix_v3_msg_conv", "conversation_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("v3_director_conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user/assistant/system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    context_snapshot_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("v3_context_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    revision_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    proposal_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("v3_action_proposals.id", ondelete="SET NULL"), nullable=True
    )
    ai_meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)  # model/tokens/耗时

    conversation: Mapped["V3DirectorConversation"] = relationship(back_populates="messages")


class V3ActionProposal(Base, TimestampMixin):
    """行动提案：AI 只能提出预定义操作类型的提案，用户确认 + 重新鉴权 + 乐观锁后才执行。

    - action_type 限定白名单；payload 结构化 diff（changes 列表）
    - base_revision_hash：提案生成时的项目 revision；应用时比对，过期则拒绝
    - lock_version：提案针对的目标资产乐观锁版本
    - status: pending/applied/dismissed/expired
    """

    __tablename__ = "v3_action_proposals"
    __table_args__ = (
        Index("ix_v3_prop_project_status", "project_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id"), nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    conversation_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("v3_director_conversations.id", ondelete="SET NULL"), nullable=True
    )
    context_snapshot_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("v3_context_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    action_type: Mapped[str] = mapped_column(String(48), nullable=False)  # 白名单见 action_proposal_service
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    target_lock_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    base_revision_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    rationale: Mapped[str] = mapped_column(Text, default="", nullable=False)
    changes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # [{field, before, after}]
    impact_refs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    applied_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    apply_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    dismissed_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
