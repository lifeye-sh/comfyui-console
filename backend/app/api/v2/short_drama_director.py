"""V3 AI 导演前期制作 API：稳定键、工作流状态、审批、故事台账、情感曲线。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.config import settings
from app.core.deps import CurrentUser, DBSession
from app.schemas.v3_director import (
    AdvanceIn,
    ApprovalDecideIn,
    ApprovalSubmitIn,
    BuildManifestIn,
    ChatMessageIn,
    ConversationCreateIn,
    CreateAuditRunIn,
    GuidanceOut,
    ManifestCompileCreateIn,
    ManifestCompilePreviewIn,
    ProposalCreateIn,
    ProposalDismissIn,
    SetGateIn,
    StableIdentityAllocateIn,
    StableIdentityOut,
    StableIdentityRetireIn,
    WaiveIssueIn,
    WorkflowStateOut,
)
from app.short_drama import ai_service, project_service
from app.short_drama.v3_director import (
    action_proposal_service,
    anchor_service,
    artifact_approval_service,
    context_selector,
    continuity_service,
    director_ai_service,
    director_workflow_service,
    ledger_service,
    manifest_compiler,
    manifest_service,
    scene_ledger_service,
    spatial_asset_service,
    stable_identity_service,
    style_bible_service,
)

router = APIRouter(
    prefix="/short-drama/projects/{project_id}/director",
    tags=["v2-short-drama-director"],
)


def _require_v3() -> None:
    if not settings.short_drama_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "短剧模块当前未启用")
    if not settings.v3_director_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "导演前期模块当前未启用")


def _owned_project(db, user, project_id):
    try:
        return project_service.owned_project(db, user.id, project_id)
    except project_service.ProjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


# ---- 工作流状态 ----

@router.get("/workflow-runs", response_model=WorkflowStateOut)
def get_workflow(project_id: int, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    return director_workflow_service.get_state(db, project_id)


@router.post("/workflow-runs", response_model=WorkflowStateOut)
def create_workflow(project_id: int, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    director_workflow_service.get_or_create_run(db, project_id)
    return director_workflow_service.get_state(db, project_id)


@router.post("/workflow-runs/advance", response_model=WorkflowStateOut)
def advance_workflow(
    project_id: int, body: AdvanceIn, user: CurrentUser, db: DBSession
) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    return director_workflow_service.advance_step(db, project_id, allow_blocked=body.allow_blocked)


@router.post("/workflow-runs/gates/{step}", response_model=WorkflowStateOut)
def set_gate(
    project_id: int, step: int, body: SetGateIn, user: CurrentUser, db: DBSession
) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    return director_workflow_service.set_gate(db, project_id, step, body.gate_status, body.reason)


# ---- 稳定键 ----

@router.get("/stable-identities", response_model=list[StableIdentityOut])
def list_identities(
    project_id: int, user: CurrentUser, db: DBSession, entity_type: str | None = None
) -> list:
    _require_v3()
    _owned_project(db, user, project_id)
    return stable_identity_service.list_by_project(db, project_id, entity_type)


@router.post("/stable-identities", response_model=StableIdentityOut, status_code=status.HTTP_201_CREATED)
def allocate_identity(
    project_id: int, body: StableIdentityAllocateIn, user: CurrentUser, db: DBSession
):
    _require_v3()
    _owned_project(db, user, project_id)
    return stable_identity_service.allocate(
        db,
        project_id=project_id,
        entity_type=body.entity_type,
        owner_id=user.id,
        created_from_type=body.created_from_type,
        created_from_id=body.created_from_id,
    )


@router.post("/stable-identities/{identity_id}/retire", response_model=StableIdentityOut)
def retire_identity(
    project_id: int, identity_id: int, body: StableIdentityRetireIn, user: CurrentUser, db: DBSession
):
    _require_v3()
    _owned_project(db, user, project_id)
    return stable_identity_service.retire(db, identity_id, body.reason or None)


# ---- 审批 ----

@router.post("/approvals", status_code=status.HTTP_201_CREATED)
def submit_approval(
    project_id: int, body: ApprovalSubmitIn, user: CurrentUser, db: DBSession
):
    _require_v3()
    _owned_project(db, user, project_id)
    d = artifact_approval_service.submit_candidate(
        db,
        project_id=project_id,
        owner_id=user.id,
        target_type=body.target_type,
        target_ref=body.target_ref,
        payload=body.payload,
        validation_errors=body.validation_errors,
        parent_approved_id=body.parent_approved_id,
    )
    return _approval_out(d)


@router.post("/approvals/{approval_id}/approve")
def approve_approval(
    project_id: int, approval_id: int, body: ApprovalDecideIn, user: CurrentUser, db: DBSession
):
    _require_v3()
    _owned_project(db, user, project_id)
    return _approval_out(artifact_approval_service.approve(db, approval_id, user.id, body.reason or None))


@router.post("/approvals/{approval_id}/reject")
def reject_approval(
    project_id: int, approval_id: int, body: ApprovalDecideIn, user: CurrentUser, db: DBSession
):
    _require_v3()
    _owned_project(db, user, project_id)
    return _approval_out(artifact_approval_service.reject(db, approval_id, user.id, body.reason))


@router.post("/approvals/{approval_id}/waive")
def waive_approval(
    project_id: int, approval_id: int, body: ApprovalDecideIn, user: CurrentUser, db: DBSession
):
    _require_v3()
    _owned_project(db, user, project_id)
    return _approval_out(artifact_approval_service.waive(db, approval_id, user.id, body.reason))


@router.get("/approvals")
def list_approvals(
    project_id: int, user: CurrentUser, db: DBSession,
    target_type: str | None = None, approval_status: str | None = None,
):
    _require_v3()
    _owned_project(db, user, project_id)
    return [_approval_out(d) for d in artifact_approval_service.list_approvals(
        db, project_id, target_type, approval_status
    )]


def _approval_out(d):
    return {
        "id": d.id,
        "project_id": d.project_id,
        "target_type": d.target_type,
        "target_ref": d.target_ref,
        "status": d.status,
        "payload": d.payload,
        "validation_errors": d.validation_errors,
        "parent_approved_id": d.parent_approved_id,
        "decided_by": d.decided_by,
        "decided_at": d.decided_at,
        "decision_reason": d.decision_reason,
        "created_at": d.created_at,
        "updated_at": d.updated_at,
    }


# ---- 故事级台账 / 情感曲线 / Checkpoint A ----

class LedgerGenerateIn(BaseModel):
    analysis_id: int
    idempotency_key: str
    provider_config_id: int | None = None


class LedgerDecisionIn(BaseModel):
    question: str
    options: list[str] = []


class LedgerDecisionResolveIn(BaseModel):
    chosen: str = ""
    note: str = ""
    waive: bool = False


def _ledger_out(ledger) -> dict:
    return {
        "id": ledger.id,
        "project_id": ledger.project_id,
        "document_id": ledger.document_id,
        "analysis_id": ledger.analysis_id,
        "version": ledger.version,
        "parent_version_id": ledger.parent_version_id,
        "status": ledger.status,
        "name": ledger.name,
        "summary": ledger.summary,
        "content": ledger.content,
        "validation_errors": ledger.validation_errors,
        "approved_by": ledger.approved_by,
        "approved_at": ledger.approved_at,
        "beat_count": len(ledger.beats),
        "created_at": ledger.created_at,
    }


@router.post("/ledgers/generate")
def generate_ledger(project_id: int, body: LedgerGenerateIn, user: CurrentUser, db: DBSession) -> dict:
    """基于已确认的小说分析生成故事台账候选（异步任务）。"""
    _require_v3()
    _owned_project(db, user, project_id)
    job = ai_service.create_story_ledger_job(
        db, user.id, project_id, body.analysis_id, body.idempotency_key, body.provider_config_id
    )
    from app.schemas.short_drama import CreativeJobOut
    return CreativeJobOut.model_validate(job).model_dump(mode="json")


@router.get("/ledgers")
def list_ledgers(project_id: int, user: CurrentUser, db: DBSession) -> list[dict]:
    _require_v3()
    _owned_project(db, user, project_id)
    from app.models import V3ScriptLedgerVersion
    ledgers = (
        db.query(V3ScriptLedgerVersion)
        .filter(V3ScriptLedgerVersion.project_id == project_id)
        .order_by(V3ScriptLedgerVersion.id.desc())
        .all()
    )
    return [_ledger_out(l) for l in ledgers]


@router.get("/ledgers/{ledger_id}")
def get_ledger_detail(project_id: int, ledger_id: int, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    ledger = ledger_service.get_ledger(db, project_id, ledger_id)
    if not ledger:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "台账不存在")
    curve = ledger_service.emotion_curve(db, ledger.id)
    out = _ledger_out(ledger)
    beats = [
        {
            "id": b.id, "stable_key": b.stable_key, "order": b.order, "event": b.event,
            "goal": b.goal, "conflict": b.conflict, "reversal": b.reversal, "outcome": b.outcome,
            "causal_dependency": b.causal_dependency, "characters": b.characters,
            "emotion_intensity": b.emotion_intensity, "emotion_valence": b.emotion_valence,
            "dominant_emotion": b.dominant_emotion, "narrative_function": b.narrative_function,
            "evidence_type": b.evidence_type, "confidence": b.confidence, "source_locator": b.source_locator,
        }
        for b in sorted(ledger.beats, key=lambda x: x.order)
    ]
    out["beats"] = beats
    out["emotion_curve"] = curve
    out["curve_summary"] = ledger_service.curve_summary(curve)
    out["decisions"] = ledger_service.decisions_to_payload(ledger_service.list_decisions(db, ledger.id))
    return out


@router.post("/ledgers/{ledger_id}/approve")
def approve_ledger(project_id: int, ledger_id: int, user: CurrentUser, db: DBSession) -> dict:
    """批准台账（Checkpoint A：必须先处理所有源材料矛盾决策）。"""
    _require_v3()
    _owned_project(db, user, project_id)
    ledger = ledger_service.get_ledger(db, project_id, ledger_id)
    if not ledger:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "台账不存在")
    try:
        ledger_service.approve(db, ledger, user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    # 批准后自动推进工作流步骤 1 门禁（若工作流存在）
    try:
        run_state = director_workflow_service.get_state(db, project_id)
        step1 = next(s for s in run_state["steps"] if s["step"] == 1)
        if step1["gate_status"] != "passed":
            director_workflow_service.set_gate(db, project_id, 1, "passed", None)
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "ledger_id": ledger.id, "status": ledger.status}


@router.post("/ledgers/{ledger_id}/decisions", status_code=status.HTTP_201_CREATED)
def create_decision(project_id: int, ledger_id: int, body: LedgerDecisionIn, user: CurrentUser, db: DBSession) -> dict:
    """手工添加 Checkpoint A 决策。"""
    _require_v3()
    _owned_project(db, user, project_id)
    ledger = ledger_service.get_ledger(db, project_id, ledger_id)
    if not ledger:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "台账不存在")
    if not body.question.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "矛盾描述不能为空")
    d = ledger_service.add_decision(db, project_id, ledger.id, user.id, body.question.strip(), body.options)
    return ledger_service.decisions_to_payload([d])[0]


@router.post("/ledger-decisions/{decision_id}/resolve")
def resolve_decision(project_id: int, decision_id: int, body: LedgerDecisionResolveIn, user: CurrentUser, db: DBSession) -> dict:
    """处理 Checkpoint A 决策（选择方案或豁免）。"""
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        d = ledger_service.resolve_decision(db, decision_id, body.chosen, body.note, body.waive)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return ledger_service.decisions_to_payload([d])[0]


# ---- 场景级台账 / 稳定键对齐 / 连续性事实 ----

class SceneSyncIn(BaseModel):
    story_version_id: int | None = None


@router.post("/scene-ledgers/sync")
def sync_scene_ledgers(project_id: int, body: SceneSyncIn, user: CurrentUser, db: DBSession) -> dict:
    """按当前分集/场景结构同步场景级台账（稳定键沿用/新增/退役）。"""
    _require_v3()
    _owned_project(db, user, project_id)
    from app.models import StoryVersion
    sv_id = body.story_version_id
    if not sv_id:
        current = db.query(StoryVersion).filter(
            StoryVersion.project_id == project_id,
            StoryVersion.is_current.is_(True),
        ).first()
        sv_id = current.id if current else None
    result = scene_ledger_service.sync_scenes_from_story_version(db, project_id, sv_id, [])
    return result


@router.get("/scene-ledgers")
def list_scene_ledgers(project_id: int, user: CurrentUser, db: DBSession) -> list[dict]:
    _require_v3()
    _owned_project(db, user, project_id)
    rows = scene_ledger_service.list_ledger_scenes(db, project_id)
    return scene_ledger_service.scene_out_payload(rows)


@router.get("/scene-ledgers/{stable_key}")
def get_scene_ledger(project_id: int, stable_key: str, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    from app.models import V3LedgerScene
    row = db.query(V3LedgerScene).filter(
        V3LedgerScene.project_id == project_id,
        V3LedgerScene.stable_key == stable_key,
    ).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "场景台账不存在")
    out = scene_ledger_service.scene_out_payload([row])[0]
    out["appearances"] = [
        {
            "character_stable_key": a.character_stable_key,
            "character_name": a.character_name,
            "costume": a.costume,
            "hair_makeup": a.hair_makeup,
            "injuries_dirt": a.injuries_dirt,
            "emotional_state": a.emotional_state,
            "change_from_previous": a.change_from_previous,
            "evidence_type": a.evidence_type,
        }
        for a in row.appearances
    ]
    out["prop_states"] = [
        {
            "prop_stable_key": p.prop_stable_key,
            "prop_name": p.prop_name,
            "owner_character_key": p.owner_character_key,
            "location_in_scene": p.location_in_scene,
            "condition": p.condition,
            "interaction": p.interaction,
            "state_change": p.state_change,
            "evidence_type": p.evidence_type,
        }
        for p in row.prop_states
    ]
    return out


class AppearanceUpsertIn(BaseModel):
    character_key: str
    character_name: str = ""
    costume: str = ""
    hair_makeup: str = ""
    injuries_dirt: str = ""
    emotional_state: str = ""
    change_from_previous: str = ""
    evidence_type: str = "inferred"
    source_locator: str = ""


class PropStateUpsertIn(BaseModel):
    prop_key: str
    prop_name: str = ""
    owner_character_key: str | None = None
    location_in_scene: str = ""
    condition: str = ""
    interaction: str = ""
    state_change: str = ""
    evidence_type: str = "inferred"
    source_locator: str = ""


@router.post("/scene-ledgers/{stable_key}/appearances")
def upsert_appearance(project_id: int, stable_key: str, body: AppearanceUpsertIn, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    from app.models import V3LedgerScene
    row = db.query(V3LedgerScene).filter(
        V3LedgerScene.project_id == project_id,
        V3LedgerScene.stable_key == stable_key,
    ).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "场景台账不存在")
    app_row = scene_ledger_service.upsert_appearance(
        db, row.id, body.character_key, body.character_name,
        {
            "costume": body.costume, "hair_makeup": body.hair_makeup,
            "injuries_dirt": body.injuries_dirt, "emotional_state": body.emotional_state,
            "change_from_previous": body.change_from_previous,
        },
        body.evidence_type, body.source_locator,
    )
    return {"ok": True, "id": app_row.id}


@router.post("/scene-ledgers/{stable_key}/prop-states")
def upsert_prop_state(project_id: int, stable_key: str, body: PropStateUpsertIn, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    from app.models import V3LedgerScene
    row = db.query(V3LedgerScene).filter(
        V3LedgerScene.project_id == project_id,
        V3LedgerScene.stable_key == stable_key,
    ).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "场景台账不存在")
    p = scene_ledger_service.upsert_prop_state(
        db, row.id, body.prop_key, body.prop_name,
        {
            "owner_character_key": body.owner_character_key or None,
            "location_in_scene": body.location_in_scene, "condition": body.condition,
            "interaction": body.interaction, "state_change": body.state_change,
        },
        body.evidence_type, body.source_locator,
    )
    return {"ok": True, "id": p.id}


class ContinuityFactIn(BaseModel):
    subject_type: str
    subject_key: str
    fact: str
    severity: str = "info"
    from_scene_key: str | None = None
    to_scene_key: str | None = None
    evidence_type: str = "inferred"
    source_locator: str = ""


class ContinuityFactResolveIn(BaseModel):
    resolution: str = ""


@router.post("/continuity-facts", status_code=status.HTTP_201_CREATED)
def add_continuity_fact(project_id: int, body: ContinuityFactIn, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        cf = scene_ledger_service.add_continuity_fact(
            db, project_id, body.subject_type, body.subject_key, body.fact,
            body.severity, body.from_scene_key, body.to_scene_key,
            evidence_type=body.evidence_type, source_locator=body.source_locator,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"id": cf.id, "severity": cf.severity, "status": cf.status}


@router.get("/continuity-facts")
def list_continuity_facts(
    project_id: int, user: CurrentUser, db: DBSession,
    severity: str | None = None, fact_status: str | None = None,
) -> list[dict]:
    _require_v3()
    _owned_project(db, user, project_id)
    from app.models import V3ContinuityFact
    q = db.query(V3ContinuityFact).filter(V3ContinuityFact.project_id == project_id)
    if severity:
        q = q.filter(V3ContinuityFact.severity == severity)
    if fact_status:
        q = q.filter(V3ContinuityFact.status == fact_status)
    severity_order = {"blocker": 0, "risk": 1, "info": 2}
    rows = q.order_by(V3ContinuityFact.id.desc()).all()
    rows.sort(key=lambda r: severity_order.get(r.severity, 3))
    return [
        {
            "id": r.id, "subject_type": r.subject_type, "subject_key": r.subject_key,
            "fact": r.fact, "severity": r.severity, "status": r.status,
            "from_scene_key": r.from_scene_key, "to_scene_key": r.to_scene_key,
            "resolution": r.resolution, "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/continuity-facts/{fact_id}/resolve")
def resolve_continuity_fact(project_id: int, fact_id: int, body: ContinuityFactResolveIn, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    from datetime import datetime, timezone

    from app.models import V3ContinuityFact
    cf = db.get(V3ContinuityFact, fact_id)
    if not cf or cf.project_id != project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "连续性事实不存在")
    cf.status = "resolved"
    cf.resolution = body.resolution
    cf.resolved_by = user.id
    cf.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "id": cf.id}


@router.get("/characters/{character_key}/trace")
def trace_character(project_id: int, character_key: str, user: CurrentUser, db: DBSession) -> list[dict]:
    """跨场景追溯角色状态变化链。"""
    _require_v3()
    _owned_project(db, user, project_id)
    return scene_ledger_service.trace_character_across_scenes(db, project_id, character_key)


# ---- 风格圣经 / 色卡 / Checkpoint B ----

class StyleBibleIn(BaseModel):
    name: str = ""
    visual_thesis: str = ""
    era: str = ""
    realism: str = ""
    composition: str = ""
    aspect_ratio: str = "9:16"
    lens_language: str = ""
    lighting: str = ""
    texture_material: str = ""
    sound_world: str = ""
    non_negotiables: list[str] = []
    reference_ids: list[int] = []
    palette: dict | None = None


class StyleDeriveIn(BaseModel):
    parent_id: int
    fields: dict = {}
    palette: dict | None = None


@router.get("/style-bibles")
def list_style_bibles(project_id: int, user: CurrentUser, db: DBSession) -> list[dict]:
    _require_v3()
    _owned_project(db, user, project_id)
    from app.models import V3PaletteVersion
    bibles = style_bible_service.list_bibles(db, project_id)
    palettes = (
        db.query(V3PaletteVersion)
        .filter(V3PaletteVersion.project_id == project_id)
        .order_by(V3PaletteVersion.id.desc())
        .all()
    )
    by_bible: dict[int, list] = {}
    for p in palettes:
        if p.style_bible_id:
            by_bible.setdefault(p.style_bible_id, []).append(p)
    return [style_bible_service.bible_out(b, by_bible.get(b.id, [])) for b in bibles]


@router.post("/style-bibles", status_code=status.HTTP_201_CREATED)
def create_style_bible(project_id: int, body: StyleBibleIn, user: CurrentUser, db: DBSession) -> dict:
    """创建风格圣经候选（最多 3 个）。"""
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        bible = style_bible_service.create_candidate(
            db, project_id, body.model_dump(), palette=body.palette, provenance={"created_by": user.id}
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return style_bible_service.bible_out(bible)


@router.post("/style-bibles/derive", status_code=status.HTTP_201_CREATED)
def derive_style_bible(project_id: int, body: StyleDeriveIn, user: CurrentUser, db: DBSession) -> dict:
    """从已批准版本派生新候选（修改批准版本的唯一方式）。"""
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        bible = style_bible_service.derive_candidate(db, body.parent_id, body.fields, body.palette)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return style_bible_service.bible_out(bible)


@router.post("/style-bibles/{style_id}/approve")
def approve_style_bible(project_id: int, style_id: int, user: CurrentUser, db: DBSession) -> dict:
    """批准风格圣经（Checkpoint B）。"""
    _require_v3()
    _owned_project(db, user, project_id)
    bible = style_bible_service.get(db, project_id, style_id)
    if not bible:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "风格圣经不存在")
    if bible.status != "candidate":
        raise HTTPException(status.HTTP_409_CONFLICT, f"当前状态 {bible.status} 不可批准")
    bible.status = "approved"
    bible.approved_by = user.id
    from datetime import datetime, timezone
    bible.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(bible)
    # 自动通过步骤 4 门禁（若工作流存在且未通过）
    try:
        run_state = director_workflow_service.get_state(db, project_id)
        step4 = next(s for s in run_state["steps"] if s["step"] == 4)
        if step4["gate_status"] != "passed":
            director_workflow_service.set_gate(db, project_id, 4, "passed", None)
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "style_id": bible.id, "status": bible.status}


@router.get("/checkpoint-b")
def check_checkpoint_b(project_id: int, user: CurrentUser, db: DBSession) -> dict:
    """Checkpoint B 状态检查。"""
    _require_v3()
    _owned_project(db, user, project_id)
    return style_bible_service.check_b(db, project_id)


# ---- 角色/道具锚点 / Checkpoint C ----

class CharacterAnchorIn(BaseModel):
    stable_key: str
    name: str = ""
    identity_anchor: dict = {}
    controllable_vars: dict = {}
    drift_prohibition: list = []
    expression_sheet: list = []
    priority: str = "supporting"
    character_id: int | None = None
    style_bible_id: int | None = None


class PropAnchorIn(BaseModel):
    stable_key: str
    name: str = ""
    size: str = ""
    material: str = ""
    wear_condition: str = ""
    owner_character_key: str | None = None
    state_changes: list = []
    drift_prohibition: list = []
    priority_rank: int = 0
    prop_id: int | None = None
    style_bible_id: int | None = None


@router.get("/character-anchors")
def list_character_anchors(
    project_id: int, user: CurrentUser, db: DBSession,
    anchor_status: str | None = None, priority: str | None = None,
) -> list[dict]:
    _require_v3()
    _owned_project(db, user, project_id)
    rows = anchor_service.list_character_anchors(db, project_id, anchor_status, priority)
    return [anchor_service.char_anchor_out(a) for a in rows]


@router.post("/character-anchors", status_code=status.HTTP_201_CREATED)
def create_character_anchor(project_id: int, body: CharacterAnchorIn, user: CurrentUser, db: DBSession) -> dict:
    """创建角色锚点候选。Checkpoint B 必须已通过；主角优先级强制。"""
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        anchor = anchor_service.create_character_anchor(
            db, project_id=project_id, stable_key=body.stable_key, name=body.name,
            identity_anchor=body.identity_anchor, controllable_vars=body.controllable_vars,
            drift_prohibition=body.drift_prohibition, priority=body.priority,
            style_bible_id=body.style_bible_id, character_id=body.character_id,
            expression_sheet=body.expression_sheet,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return anchor_service.char_anchor_out(anchor)


@router.post("/character-anchors/{anchor_id}/approve")
def approve_character_anchor(project_id: int, anchor_id: int, user: CurrentUser, db: DBSession) -> dict:
    """Checkpoint C 逐实体批准角色锚点。"""
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        anchor = anchor_service.approve_character_anchor(db, project_id, anchor_id, user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return anchor_service.char_anchor_out(anchor)


@router.get("/prop-anchors")
def list_prop_anchors(project_id: int, user: CurrentUser, db: DBSession, anchor_status: str | None = None) -> list[dict]:
    _require_v3()
    _owned_project(db, user, project_id)
    rows = anchor_service.list_prop_anchors(db, project_id, anchor_status)
    return [anchor_service.prop_anchor_out(a) for a in rows]


@router.post("/prop-anchors", status_code=status.HTTP_201_CREATED)
def create_prop_anchor(project_id: int, body: PropAnchorIn, user: CurrentUser, db: DBSession) -> dict:
    """创建道具锚点候选。"""
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        anchor = anchor_service.create_prop_anchor(
            db, project_id=project_id, stable_key=body.stable_key, name=body.name,
            fields={
                "size": body.size, "material": body.material,
                "wear_condition": body.wear_condition,
                "owner_character_key": body.owner_character_key,
                "state_changes": body.state_changes,
                "drift_prohibition": body.drift_prohibition,
                "priority_rank": body.priority_rank,
            },
            style_bible_id=body.style_bible_id, prop_id=body.prop_id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return anchor_service.prop_anchor_out(anchor)


@router.post("/prop-anchors/{anchor_id}/approve")
def approve_prop_anchor(project_id: int, anchor_id: int, user: CurrentUser, db: DBSession) -> dict:
    """Checkpoint C 逐实体批准道具锚点。"""
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        anchor = anchor_service.approve_prop_anchor(db, project_id, anchor_id, user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return anchor_service.prop_anchor_out(anchor)


@router.get("/checkpoint-c")
def check_checkpoint_c(project_id: int, user: CurrentUser, db: DBSession) -> dict:
    """Checkpoint C 状态检查。"""
    _require_v3()
    _owned_project(db, user, project_id)
    return anchor_service.checkpoint_c_status(db, project_id)


# ---- 空间拓扑 / 内景平面图 / 关键视图 ----

class SpatialPlanIn(BaseModel):
    location_stable_key: str
    plan_kind: str = "exterior"  # exterior/interior
    name: str = ""
    topology: dict = {}
    floor_plan: dict = {}
    location_id: int | None = None
    parent_version_id: int | None = None


class LocationViewIn(BaseModel):
    name: str = ""
    description: str = ""
    view_angle: str = ""
    resource_id: int | None = None


@router.get("/spatial-plans")
def list_spatial_plans(project_id: int, user: CurrentUser, db: DBSession) -> list[dict]:
    _require_v3()
    _owned_project(db, user, project_id)
    return [spatial_asset_service.plan_out(p) for p in spatial_asset_service.list_plans(db, project_id)]


@router.post("/spatial-plans", status_code=status.HTTP_201_CREATED)
def create_spatial_plan(project_id: int, body: SpatialPlanIn, user: CurrentUser, db: DBSession) -> dict:
    """创建空间结构版本候选。外景=拓扑，内景=平面图。"""
    _require_v3()
    _owned_project(db, user, project_id)
    if body.plan_kind not in ("exterior", "interior"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "plan_kind 必须是 exterior 或 interior")
    plan, errors = spatial_asset_service.create_plan(
        db,
        project_id=project_id,
        location_stable_key=body.location_stable_key,
        plan_kind=body.plan_kind,
        name=body.name,
        topology=body.topology,
        floor_plan=body.floor_plan,
        location_id=body.location_id,
        parent_version_id=body.parent_version_id,
        provenance={"created_by": user.id},
    )
    out = spatial_asset_service.plan_out(plan)
    out["validation_errors"] = errors
    return out


@router.post("/spatial-plans/{plan_id}/approve")
def approve_spatial_plan(project_id: int, plan_id: int, user: CurrentUser, db: DBSession) -> dict:
    """批准空间结构版本。批准后旧关键视图自动标记 stale。"""
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        plan = spatial_asset_service.approve_plan(db, project_id, plan_id, user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"ok": True, "plan_id": plan.id, "status": plan.status}


@router.get("/spatial-plans/{plan_id}/views")
def list_location_views(project_id: int, plan_id: int, user: CurrentUser, db: DBSession) -> list[dict]:
    _require_v3()
    _owned_project(db, user, project_id)
    return [spatial_asset_service.view_out(v) for v in spatial_asset_service.list_views(db, project_id, plan_id)]


@router.post("/spatial-plans/{plan_id}/views", status_code=status.HTTP_201_CREATED)
def create_location_view(project_id: int, plan_id: int, body: LocationViewIn, user: CurrentUser, db: DBSession) -> dict:
    """创建关键视图（必须挂在空间结构版本下）。"""
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        view = spatial_asset_service.create_view(
            db, project_id, plan_id, body.name, body.description,
            body.view_angle, body.resource_id, {"created_by": user.id},
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return spatial_asset_service.view_out(view)


@router.post("/location-views/{view_id}/approve")
def approve_location_view(project_id: int, view_id: int, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        view = spatial_asset_service.approve_view(db, project_id, view_id, user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return spatial_asset_service.view_out(view)


# ============ 第 7 轮：依赖图 / Manifest / 连续性审计 ============

# ---- 依赖图与 Stale 传播 ----

@router.post("/dependency-graph/build")
def build_dependency_graph(project_id: int, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    count = manifest_service.build_dependency_graph(db, project_id)
    return {"ok": True, "edges_built": count}

@router.get("/dependencies")
def list_dependencies(project_id: int, user: CurrentUser, db: DBSession) -> list[dict]:
    _require_v3()
    _owned_project(db, user, project_id)
    return [manifest_service.dependency_out(d) for d in manifest_service.list_dependencies(db, project_id)]

@router.get("/stale-records")
def list_stale_records(project_id: int, user: CurrentUser, db: DBSession, status: str | None = None) -> list[dict]:
    _require_v3()
    _owned_project(db, user, project_id)
    return [manifest_service.stale_out(r) for r in manifest_service.list_stale_records(db, project_id, status)]

# ---- Manifest ----

@router.post("/manifests")
def build_manifest(project_id: int, body: BuildManifestIn, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    m = manifest_service.build_manifest_from_approved(db, project_id, body.notes)
    return manifest_service.manifest_out(m, m.items)

@router.get("/manifests")
def list_manifests(project_id: int, user: CurrentUser, db: DBSession) -> list[dict]:
    _require_v3()
    _owned_project(db, user, project_id)
    return [manifest_service.manifest_out(m) for m in manifest_service.list_manifests(db, project_id)]

@router.get("/manifests/{manifest_id}")
def get_manifest(project_id: int, manifest_id: int, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    m = manifest_service.get_manifest(db, project_id, manifest_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Manifest 不存在")
    return manifest_service.manifest_out(m, m.items)

@router.post("/manifests/{manifest_id}/approve")
def approve_manifest(project_id: int, manifest_id: int, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        m = manifest_service.approve_manifest(db, project_id, manifest_id, user.id)
        return manifest_service.manifest_out(m)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

# ---- 连续性审计 ----

@router.post("/audit-runs")
def create_audit_run(project_id: int, body: CreateAuditRunIn, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    run = continuity_service.create_audit_run(db, project_id, body.manifest_version_id)
    return continuity_service.run_out(run)

@router.get("/audit-runs")
def list_audit_runs(project_id: int, user: CurrentUser, db: DBSession) -> list[dict]:
    _require_v3()
    _owned_project(db, user, project_id)
    return [continuity_service.run_out(r) for r in continuity_service.list_audit_runs(db, project_id)]

@router.get("/audit-runs/{run_id}")
def get_audit_run(project_id: int, run_id: int, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    run = continuity_service.get_audit_run(db, project_id, run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Audit Run 不存在")
    return continuity_service.run_out(run)

@router.post("/audit-runs/{run_id}/run-rules")
def run_rule_audit(project_id: int, run_id: int, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    run = continuity_service.get_audit_run(db, project_id, run_id)
    if not run or run.status != "running":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Audit Run 不可用")
    count = continuity_service.run_rule_audit(db, project_id, run)
    return {"ok": True, "issues_found": count}

@router.post("/audit-runs/{run_id}/run-llm")
def run_llm_audit(project_id: int, run_id: int, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    run = continuity_service.get_audit_run(db, project_id, run_id)
    if not run or run.status != "running":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Audit Run 不可用")
    count = continuity_service.run_llm_audit(db, project_id, run)
    return {"ok": True, "issues_found": count}

@router.post("/audit-runs/{run_id}/finish")
def finish_audit(project_id: int, run_id: int, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    run = continuity_service.get_audit_run(db, project_id, run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Audit Run 不存在")
    run = continuity_service.finish_audit(db, run)
    return continuity_service.run_out(run)

@router.post("/audit-issues/{issue_id}/waive")
def waive_issue(project_id: int, issue_id: int, body: WaiveIssueIn, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        issue = continuity_service.waive_issue(db, issue_id, user.id, body.reason)
        return continuity_service.issue_out(issue)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

@router.get("/detected-gaps")
def list_detected_gaps(project_id: int, user: CurrentUser, db: DBSession) -> list[dict]:
    _require_v3()
    _owned_project(db, user, project_id)
    from app.schemas.v3_director import DetectedGapOut
    return [DetectedGapOut.model_validate(g).model_dump() for g in continuity_service.list_gaps(db, project_id)]


# ============ 第 7 轮：依赖图 / Manifest / 连续性审计 ============

# ---- 依赖图 ----

@router.post("/dependency-graph/build")
def build_dependency_graph(project_id: int, user: CurrentUser, db: DBSession) -> dict:
    """确定性规则建立 ArtifactDependency 边。"""
    _require_v3()
    _owned_project(db, user, project_id)
    count = manifest_service.build_dependency_graph(db, project_id)
    return {"ok": True, "edges": count}


@router.get("/dependencies")
def list_dependencies(project_id: int, user: CurrentUser, db: DBSession) -> list[dict]:
    _require_v3()
    _owned_project(db, user, project_id)
    return [manifest_service.dependency_out(d) for d in manifest_service.list_dependencies(db, project_id)]


# ---- Stale 记录 ----

@router.get("/stale-records")
def list_stale_records(
    project_id: int, user: CurrentUser, db: DBSession, status: str | None = None
) -> list[dict]:
    _require_v3()
    _owned_project(db, user, project_id)
    return [manifest_service.stale_out(r) for r in manifest_service.list_stale_records(db, project_id, status)]


@router.post("/stale-records/{stale_id}/resolve")
def resolve_stale_record(
    project_id: int, stale_id: int, body: dict, user: CurrentUser, db: DBSession
) -> dict:
    """处理过期记录。"""
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        rec = manifest_service.resolve_stale(db, stale_id, user.id, body.get("resolution", ""))
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return manifest_service.stale_out(rec)


# ---- Manifest ----

@router.post("/manifests", status_code=status.HTTP_201_CREATED)
def build_manifest(
    project_id: int, body: BuildManifestIn, user: CurrentUser, db: DBSession
) -> dict:
    """从已批准资产自动生成清单。"""
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        m = manifest_service.build_manifest_from_approved(db, project_id, body.notes)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return manifest_service.manifest_out(m, m.items)


@router.get("/manifests")
def list_manifests(project_id: int, user: CurrentUser, db: DBSession) -> list[dict]:
    _require_v3()
    _owned_project(db, user, project_id)
    return [manifest_service.manifest_out(m) for m in manifest_service.list_manifests(db, project_id)]


@router.get("/manifests/{manifest_id}")
def get_manifest(project_id: int, manifest_id: int, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    m = manifest_service.get_manifest(db, project_id, manifest_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "清单不存在")
    return manifest_service.manifest_out(m, m.items)


@router.post("/manifests/{manifest_id}/approve")
def approve_manifest(
    project_id: int, manifest_id: int, user: CurrentUser, db: DBSession
) -> dict:
    """审批清单（仅 draft 可审批）。"""
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        m = manifest_service.approve_manifest(db, project_id, manifest_id, user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return manifest_service.manifest_out(m, m.items)


# ---- 审计 ----

@router.post("/audit-runs", status_code=status.HTTP_201_CREATED)
def create_audit_run(
    project_id: int, body: CreateAuditRunIn, user: CurrentUser, db: DBSession
) -> dict:
    """创建审计运行。"""
    _require_v3()
    _owned_project(db, user, project_id)
    run = continuity_service.create_audit_run(db, project_id, body.manifest_version_id)
    return continuity_service.run_out(run)


@router.get("/audit-runs")
def list_audit_runs(project_id: int, user: CurrentUser, db: DBSession) -> list[dict]:
    _require_v3()
    _owned_project(db, user, project_id)
    return [continuity_service.run_out(r) for r in continuity_service.list_audit_runs(db, project_id)]


@router.get("/audit-runs/{run_id}")
def get_audit_run(project_id: int, run_id: int, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    run = continuity_service.get_audit_run(db, project_id, run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "审计运行不存在")
    return continuity_service.run_out(run)


@router.post("/audit-runs/{run_id}/run-rules")
def run_rule_audit(project_id: int, run_id: int, user: CurrentUser, db: DBSession) -> dict:
    """运行确定性规则审计。"""
    _require_v3()
    _owned_project(db, user, project_id)
    run = continuity_service.get_audit_run(db, project_id, run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "审计运行不存在")
    count = continuity_service.run_rule_audit(db, project_id, run)
    return {"ok": True, "rule_issues": count}


@router.post("/audit-runs/{run_id}/run-llm")
def run_llm_audit(project_id: int, run_id: int, user: CurrentUser, db: DBSession) -> dict:
    """运行 AI 语义审计补充。"""
    _require_v3()
    _owned_project(db, user, project_id)
    run = continuity_service.get_audit_run(db, project_id, run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "审计运行不存在")
    count = continuity_service.run_llm_audit(db, project_id, run)
    return {"ok": True, "llm_issues": count}


@router.post("/audit-runs/{run_id}/finish")
def finish_audit(project_id: int, run_id: int, user: CurrentUser, db: DBSession) -> dict:
    """结束审计运行并生成汇总。"""
    _require_v3()
    _owned_project(db, user, project_id)
    run = continuity_service.get_audit_run(db, project_id, run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "审计运行不存在")
    run = continuity_service.finish_audit(db, run)
    return continuity_service.run_out(run)


@router.post("/audit-issues/{issue_id}/waive")
def waive_audit_issue(
    project_id: int, issue_id: int, body: WaiveIssueIn, user: CurrentUser, db: DBSession
) -> dict:
    """豁免审计问题（需提供原因）。"""
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        issue = continuity_service.waive_issue(db, issue_id, user.id, body.reason)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return continuity_service.issue_out(issue)


# ---- 检测缺口 ----

@router.get("/detected-gaps")
def list_detected_gaps(project_id: int, user: CurrentUser, db: DBSession) -> list[dict]:
    _require_v3()
    _owned_project(db, user, project_id)
    gaps = continuity_service.list_gaps(db, project_id)
    return [
        {
            "id": g.id, "gap_type": g.gap_type, "description": g.description,
            "suggested_fix": g.suggested_fix, "affected_refs": g.affected_refs,
            "status": g.status, "created_at": g.created_at,
        }
        for g in gaps
    ]


# ============ 第 8 轮：Manifest 编译 / 生产链路 ============

@router.post("/manifests/{manifest_id}/compile-preview")
def compile_manifest_preview(
    project_id: int, manifest_id: int, body: ManifestCompilePreviewIn, user: CurrentUser, db: DBSession
) -> dict:
    """编译预览：返回逐条 ProductionIntent 与校验结果，不创建任务。"""
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        return manifest_compiler.compile_preview(
            db, user.id, project_id, manifest_id,
            body.generation_type_id, body.workflow_version_id,
            body.item_ids or None, body.parameter_overrides, body.item_parameter_overrides,
        )
    except manifest_compiler.ManifestCompileError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/manifests/{manifest_id}/create-tasks")
def create_tasks_from_manifest(
    project_id: int, manifest_id: int, body: ManifestCompileCreateIn, user: CurrentUser, db: DBSession
) -> dict:
    """从已审批 Manifest 创建生产任务（幂等）。校验失败整批拒绝。"""
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        return manifest_compiler.create_tasks_from_manifest(
            db, user.id, project_id, manifest_id,
            body.generation_type_id, body.workflow_version_id,
            body.idempotency_key, body.submit,
            body.item_ids or None, body.parameter_overrides, body.item_parameter_overrides,
        )
    except manifest_compiler.ManifestCompileError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/manifests/{manifest_id}/task-links")
def manifest_task_links(project_id: int, manifest_id: int, user: CurrentUser, db: DBSession) -> list[dict]:
    """查看 Manifest 全部任务链接与任务执行状态。"""
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        return manifest_compiler.manifest_task_links(db, user.id, project_id, manifest_id)
    except manifest_compiler.ManifestCompileError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/manifests/{manifest_id}/refresh-status")
def refresh_manifest_status(project_id: int, manifest_id: int, user: CurrentUser, db: DBSession) -> dict:
    """根据任务执行状态刷新 ManifestItem 状态（Take 回写后同步）。"""
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        return manifest_compiler.refresh_manifest_status(db, user.id, project_id, manifest_id)
    except manifest_compiler.ManifestCompileError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


# ============ 第 9 轮：AI 导演对话 / 建议 / 提案 ============

# ---- 建议（右栏 GuidancePanel）----

@router.get("/context-snapshot")
def get_context_snapshot(project_id: int, user: CurrentUser, db: DBSession, purpose: str = "guidance") -> dict:
    """获取（或复用同 revision 的）项目上下文快照。"""
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        snapshot = context_selector.create_snapshot(db, project_id, purpose)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return context_selector.snapshot_out(snapshot)


@router.post("/guidance", response_model=GuidanceOut)
def generate_guidance(project_id: int, user: CurrentUser, db: DBSession) -> dict:
    """AI 生成右栏建议（缺失/审计/stale）。revision guard 基于快照。"""
    _require_v3()
    _owned_project(db, user, project_id)
    snapshot = context_selector.create_snapshot(db, project_id, "guidance")
    try:
        return director_ai_service.generate_guidance(db, user.id, snapshot)
    except director_ai_service.RateLimitError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc
    except ai_service.AIResponseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


# ---- 对话（底部 DirectorChat）----

@router.post("/conversations", status_code=status.HTTP_201_CREATED)
def create_conversation(project_id: int, body: ConversationCreateIn, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    from app.models import V3DirectorConversation
    conv = V3DirectorConversation(
        project_id=project_id, owner_id=user.id,
        title=(body.title or "新对话")[:160],
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return {"id": conv.id, "project_id": conv.project_id, "title": conv.title,
            "status": conv.status, "created_at": conv.created_at, "messages": []}


@router.get("/conversations")
def list_conversations(project_id: int, user: CurrentUser, db: DBSession) -> list[dict]:
    """仅返回当前用户自己的会话（owner 隔离）。"""
    _require_v3()
    _owned_project(db, user, project_id)
    from app.models import V3DirectorConversation
    convs = (
        db.query(V3DirectorConversation)
        .filter(
            V3DirectorConversation.project_id == project_id,
            V3DirectorConversation.owner_id == user.id,
        )
        .order_by(V3DirectorConversation.id.desc())
        .limit(50)
        .all()
    )
    return [
        {"id": c.id, "project_id": c.project_id, "title": c.title,
         "status": c.status, "created_at": c.created_at, "messages": []}
        for c in convs
    ]


@router.get("/conversations/{conversation_id}")
def get_conversation(project_id: int, conversation_id: int, user: CurrentUser, db: DBSession) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    from app.models import V3DirectorConversation
    conv = db.query(V3DirectorConversation).filter(
        V3DirectorConversation.id == conversation_id,
        V3DirectorConversation.project_id == project_id,
        V3DirectorConversation.owner_id == user.id,
    ).first()
    if not conv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    return {
        "id": conv.id, "project_id": conv.project_id, "title": conv.title,
        "status": conv.status, "created_at": conv.created_at,
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content,
             "revision_hash": m.revision_hash, "proposal_id": m.proposal_id,
             "ai_meta": m.ai_meta, "created_at": m.created_at}
            for m in conv.messages
        ],
    }


@router.post("/conversations/{conversation_id}/messages", status_code=status.HTTP_201_CREATED)
def send_chat_message(
    project_id: int, conversation_id: int, body: ChatMessageIn, user: CurrentUser, db: DBSession
) -> dict:
    """发送用户消息并获取 AI 回复。AI 结果绑定 context revision（revision guard）。"""
    _require_v3()
    _owned_project(db, user, project_id)
    from app.core.events import publish_director_event
    from app.models import V3DirectorConversation, V3DirectorMessage

    conv = db.query(V3DirectorConversation).filter(
        V3DirectorConversation.id == conversation_id,
        V3DirectorConversation.project_id == project_id,
        V3DirectorConversation.owner_id == user.id,
    ).first()
    if not conv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")

    snapshot = context_selector.create_snapshot(db, project_id, "chat")
    history = [
        {"role": m.role, "content": m.content}
        for m in conv.messages[-20:]
    ]
    user_msg = V3DirectorMessage(
        conversation_id=conv.id, role="user", content=body.content,
        revision_hash=snapshot.revision_hash,
    )
    db.add(user_msg)
    db.commit()

    try:
        reply_text, ai_meta = director_ai_service.generate_chat_reply(
            db, user.id, snapshot, history, body.content,
        )
    except director_ai_service.RateLimitError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc
    except ai_service.AIResponseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    assistant_msg = V3DirectorMessage(
        conversation_id=conv.id, role="assistant", content=reply_text,
        context_snapshot_id=snapshot.id, revision_hash=snapshot.revision_hash,
        ai_meta=ai_meta,
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)

    from app.short_drama.v3_director import director_ws_publish
    director_ws_publish.safe_publish(
        project_id, user.id, "chat_reply",
        {"conversation_id": conv.id, "message_id": assistant_msg.id},
    )

    return {
        "id": assistant_msg.id, "role": assistant_msg.role,
        "content": assistant_msg.content,
        "revision_hash": assistant_msg.revision_hash,
        "proposal_id": None, "ai_meta": ai_meta,
        "created_at": assistant_msg.created_at,
    }


# ---- 提案（ActionProposal：确认/忽略/审计）----

@router.get("/action-proposals")
def list_action_proposals(project_id: int, user: CurrentUser, db: DBSession, status_filter: str | None = None) -> list[dict]:
    _require_v3()
    _owned_project(db, user, project_id)
    # 先批处理过期提案（revision guard）
    action_proposal_service.mark_expired_proposals(db, project_id)
    proposals = action_proposal_service.list_proposals(db, user.id, project_id, status_filter)
    return [action_proposal_service.proposal_out(db, p) for p in proposals]


@router.post("/action-proposals/generate", status_code=status.HTTP_201_CREATED)
def generate_proposals(project_id: int, user: CurrentUser, db: DBSession) -> list[dict]:
    """AI 生成提案（白名单过滤），逐条入库为 pending。"""
    _require_v3()
    _owned_project(db, user, project_id)
    snapshot = context_selector.create_snapshot(db, project_id, "proposal")
    try:
        raw = director_ai_service.generate_proposals(db, user.id, snapshot)
    except director_ai_service.RateLimitError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc
    except ai_service.AIResponseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    created = []
    for data in raw:
        try:
            proposal = action_proposal_service.create_proposal(
                db, user.id, project_id, snapshot, data,
            )
            created.append(proposal)
        except action_proposal_service.ProposalError:
            continue
    return [action_proposal_service.proposal_out(db, p) for p in created]


@router.post("/action-proposals/{proposal_id}/apply")
def apply_action_proposal(project_id: int, proposal_id: int, user: CurrentUser, db: DBSession) -> dict:
    """应用提案：确认 + 重新鉴权 + revision guard + 乐观锁 + 执行审计。"""
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        proposal = action_proposal_service.apply_proposal(db, user.id, project_id, proposal_id)
    except action_proposal_service.ProposalExpiredError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"EXPIRED:{exc}") from exc
    except action_proposal_service.ProposalError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return action_proposal_service.proposal_out(db, proposal)


@router.post("/action-proposals/{proposal_id}/dismiss")
def dismiss_action_proposal(
    project_id: int, proposal_id: int, body: ProposalDismissIn, user: CurrentUser, db: DBSession
) -> dict:
    _require_v3()
    _owned_project(db, user, project_id)
    try:
        proposal = action_proposal_service.dismiss_proposal(
            db, user.id, project_id, proposal_id, body.reason,
        )
    except action_proposal_service.ProposalError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return action_proposal_service.proposal_out(db, proposal)
