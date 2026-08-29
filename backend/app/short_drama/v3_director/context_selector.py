"""ContextSelector：按用途构建任务相关上下文快照。

契约见实施计划第 9 轮：
- 任务相关 ContextSnapshot、token budget、hash 和截断记录
- 相同 (project, revision) 的分析任务可合并（revision_hash 相同即复用）
- 新 revision 出现时旧快照标记 superseded
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    V3ActionProposal,
    V3AuditRun,
    V3CharacterAnchorVersion,
    V3ContextSnapshot,
    V3DetectedGap,
    V3GenerationManifest,
    V3LedgerScene,
    V3PropAnchorVersion,
    V3StaleRecord,
    V3StyleBibleVersion,
)

PURPOSES = ("guidance", "chat", "proposal", "audit")

DEFAULT_TOKEN_BUDGET = 4000


def estimate_tokens(data: Any) -> int:
    """粗略 token 估算：中文约 1 字/token，英文约 4 字符/token。取 JSON 长度加权。"""
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, default=str)
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    other = len(text) - cjk
    return cjk + max(1, other // 4)


def compute_revision_hash(db: Session, project_id: int) -> str:
    """项目关键资产的 revision 指纹：任一上游资产变更都会改变 hash。

    纳入：风格圣经最新版本 id、角色/道具锚点版本 id + lock_version + 内容摘要、
    场景台账更新时间、最新 manifest 版本 id。
    """
    style = (
        db.query(V3StyleBibleVersion.id, V3StyleBibleVersion.lock_version, V3StyleBibleVersion.visual_thesis)
        .filter(V3StyleBibleVersion.project_id == project_id)
        .order_by(V3StyleBibleVersion.id.desc())
        .first()
    )
    char_versions = (
        db.query(
            V3CharacterAnchorVersion.stable_key,
            V3CharacterAnchorVersion.id,
            V3CharacterAnchorVersion.lock_version,
            V3CharacterAnchorVersion.controllable_vars,
        )
        .filter(V3CharacterAnchorVersion.project_id == project_id)
        .order_by(V3CharacterAnchorVersion.id.desc())
        .limit(50)
        .all()
    )
    prop_versions = (
        db.query(
            V3PropAnchorVersion.stable_key,
            V3PropAnchorVersion.id,
            V3PropAnchorVersion.lock_version,
            V3PropAnchorVersion.wear_condition,
        )
        .filter(V3PropAnchorVersion.project_id == project_id)
        .order_by(V3PropAnchorVersion.id.desc())
        .limit(50)
        .all()
    )
    manifest = (
        db.query(V3GenerationManifest.id, V3GenerationManifest.version)
        .filter(V3GenerationManifest.project_id == project_id)
        .order_by(V3GenerationManifest.id.desc())
        .first()
    )
    scene_max = (
        db.query(V3LedgerScene.updated_at)
        .filter(V3LedgerScene.project_id == project_id)
        .order_by(V3LedgerScene.updated_at.desc())
        .first()
    )
    fingerprint = {
        "style": [str(x) for x in style] if style else None,
        "chars": [
            (r.stable_key, r.id, r.lock_version, json.dumps(r.controllable_vars, ensure_ascii=False, sort_keys=True))
            for r in char_versions
        ],
        "props": [
            (r.stable_key, r.id, r.lock_version, r.wear_condition)
            for r in prop_versions
        ],
        "manifest": list(manifest) if manifest else None,
        "scene_updated": str(scene_max[0]) if scene_max else None,
    }
    raw = json.dumps(fingerprint, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def build_context(db: Session, project_id: int, purpose: str) -> dict[str, Any]:
    """构建任务相关上下文（结构化 dict，不含无关项目数据）。"""
    if purpose not in PURPOSES:
        raise ValueError(f"未知上下文用途：{purpose}")

    context: dict[str, Any] = {"purpose": purpose}

    style = (
        db.query(V3StyleBibleVersion)
        .filter(V3StyleBibleVersion.project_id == project_id, V3StyleBibleVersion.status == "approved")
        .order_by(V3StyleBibleVersion.id.desc())
        .first()
    )
    if style:
        context["style"] = {
            "name": style.name, "visual_thesis": style.visual_thesis,
            "aspect_ratio": style.aspect_ratio, "era": style.era,
        }

    # guidance/audit 用途包含缺口、审计问题、stale 概要
    if purpose in ("guidance", "audit"):
        gaps = (
            db.query(V3DetectedGap)
            .filter(V3DetectedGap.project_id == project_id, V3DetectedGap.status == "open")
            .order_by(V3DetectedGap.id.desc())
            .limit(20)
            .all()
        )
        context["gaps"] = [
            {"gap_type": g.gap_type, "description": g.description, "suggested_fix": g.suggested_fix}
            for g in gaps
        ]
        run = (
            db.query(V3AuditRun)
            .filter(V3AuditRun.project_id == project_id, V3AuditRun.status == "completed")
            .order_by(V3AuditRun.id.desc())
            .first()
        )
        if run:
            context["latest_audit"] = {
                "run_id": run.id, "summary": run.summary,
                "open_blockers": (run.summary or {}).get("blockers", 0),
            }
        stale = (
            db.query(V3StaleRecord)
            .filter(V3StaleRecord.project_id == project_id, V3StaleRecord.status == "open")
            .limit(20)
            .all()
        )
        context["stale_assets"] = [
            {"asset_type": s.asset_type, "asset_ref": s.asset_ref, "reason": s.stale_reason}
            for s in stale
        ]

    # proposal 用途包含可编辑目标（锚点/场景台账）与在途提案
    if purpose == "proposal":
        chars = (
            db.query(V3CharacterAnchorVersion)
            .filter(V3CharacterAnchorVersion.project_id == project_id, V3CharacterAnchorVersion.status == "approved")
            .order_by(V3CharacterAnchorVersion.id.desc())
            .limit(30)
            .all()
        )
        context["editable_targets"] = [
            {
                "type": "character_anchor", "ref": c.stable_key, "name": c.name,
                "lock_version": c.lock_version,
                "controllable_vars": c.controllable_vars,
            }
            for c in chars
        ]
        pending = (
            db.query(V3ActionProposal)
            .filter(V3ActionProposal.project_id == project_id, V3ActionProposal.status == "pending")
            .limit(20)
            .all()
        )
        context["pending_proposals"] = [
            {"id": p.id, "action_type": p.action_type, "target": f"{p.target_type}:{p.target_ref}"}
            for p in pending
        ]

    return context


def create_snapshot(
    db: Session,
    project_id: int,
    purpose: str,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
) -> V3ContextSnapshot:
    """构建并持久化上下文快照；同 revision 旧快照标记 superseded。

    超出 token 预算时按区块优先级截断，并记录截断说明。
    """
    revision_hash = compute_revision_hash(db, project_id)

    # 复用：同 (project, purpose, revision) 且未 superseded 的最新快照
    existing = (
        db.query(V3ContextSnapshot)
        .filter(
            V3ContextSnapshot.project_id == project_id,
            V3ContextSnapshot.purpose == purpose,
            V3ContextSnapshot.revision_hash == revision_hash,
            V3ContextSnapshot.superseded.is_(False),
        )
        .order_by(V3ContextSnapshot.id.desc())
        .first()
    )
    if existing:
        return existing

    # 旧 revision 快照标记 superseded（revision guard）
    db.query(V3ContextSnapshot).filter(
        V3ContextSnapshot.project_id == project_id,
        V3ContextSnapshot.purpose == purpose,
        V3ContextSnapshot.superseded.is_(False),
    ).update({V3ContextSnapshot.superseded: True}, synchronize_session=False)

    context = build_context(db, project_id, purpose)

    token_estimated = estimate_tokens(context)
    truncated = False
    truncation_note = ""
    if token_estimated > token_budget:
        truncated = True
        # 按优先级保留：style > gaps > stale_assets > latest_audit
        for drop_key in ("latest_audit", "stale_assets", "gaps"):
            if token_estimated <= token_budget:
                break
            dropped = context.pop(drop_key, None)
            if dropped:
                truncation_note = f"截断区块 {drop_key}；"
                token_estimated = estimate_tokens(context)
        truncation_note = truncation_note or "上下文超出预算"

    snapshot = V3ContextSnapshot(
        project_id=project_id,
        purpose=purpose,
        revision_hash=revision_hash,
        content=context,
        token_budget=token_budget,
        token_estimated=token_estimated,
        truncated=truncated,
        truncation_note=truncation_note,
        superseded=False,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def snapshot_out(snapshot: V3ContextSnapshot) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "project_id": snapshot.project_id,
        "purpose": snapshot.purpose,
        "revision_hash": snapshot.revision_hash,
        "token_budget": snapshot.token_budget,
        "token_estimated": snapshot.token_estimated,
        "truncated": snapshot.truncated,
        "truncation_note": snapshot.truncation_note,
        "superseded": snapshot.superseded,
        "content": snapshot.content,
        "created_at": snapshot.created_at,
    }
