"""ActionProposal 服务：提案创建、应用（重新鉴权 + 乐观锁 + revision guard）、忽略、审计。

契约见实施计划第 9 轮：
- 生成 diff、用户确认、重新鉴权、乐观锁和执行审计
- ActionProposal 在版本过期时拒绝执行并要求重新生成
- 旧 revision AI 结果不能改变当前状态
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog, User, V3ActionProposal, V3CharacterAnchorVersion, V3ContextSnapshot, V3PropAnchorVersion
from app.short_drama.v3_director import context_selector
from app.short_drama.v3_director.director_ai_service import ACTION_TYPES


class ProposalError(ValueError):
    pass


class ProposalExpiredError(ProposalError):
    """revision 过期 / 乐观锁冲突。"""


def create_proposal(
    db: Session,
    owner_id: int,
    project_id: int,
    snapshot: V3ContextSnapshot,
    data: dict[str, Any],
    conversation_id: int | None = None,
) -> V3ActionProposal:
    """从 AI 输出创建提案（director_ai_service 已做白名单过滤，这里做二次校验）。"""
    action_type = str(data.get("action_type", ""))
    spec = ACTION_TYPES.get(action_type)
    if spec is None:
        raise ProposalError(f"未定义操作类型：{action_type}")

    # 二次校验目标归属：目标必须是本项目资产
    target_ref = str(data.get("target_ref", ""))
    target = _resolve_target(db, project_id, spec["target_type"], target_ref)
    if target is None:
        raise ProposalError(f"目标资产不存在：{spec['target_type']}:{target_ref}")

    proposal = V3ActionProposal(
        project_id=project_id,
        owner_id=owner_id,
        conversation_id=conversation_id,
        context_snapshot_id=snapshot.id,
        action_type=action_type,
        target_type=spec["target_type"],
        target_ref=target_ref,
        target_lock_version=getattr(target, "lock_version", 0),
        base_revision_hash=snapshot.revision_hash,
        title=str(data.get("title", ""))[:200],
        rationale=str(data.get("rationale", "")),
        changes=data.get("changes", []),
        impact_refs=data.get("impact_refs", []),
        status="pending",
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return proposal


def _resolve_target(db: Session, project_id: int, target_type: str, target_ref: str):
    """重新鉴权时也会用到：解析并校验目标归属本项目。"""
    if target_type == "character_anchor":
        return (
            db.query(V3CharacterAnchorVersion)
            .filter(
                V3CharacterAnchorVersion.project_id == project_id,
                V3CharacterAnchorVersion.stable_key == target_ref,
                V3CharacterAnchorVersion.status == "approved",
            )
            .order_by(V3CharacterAnchorVersion.id.desc())
            .first()
        )
    if target_type == "prop_anchor":
        return (
            db.query(V3PropAnchorVersion)
            .filter(
                V3PropAnchorVersion.project_id == project_id,
                V3PropAnchorVersion.stable_key == target_ref,
                V3PropAnchorVersion.status == "approved",
            )
            .order_by(V3PropAnchorVersion.id.desc())
            .first()
        )
    return None


def apply_proposal(db: Session, user_id: int, project_id: int, proposal_id: int) -> V3ActionProposal:
    """应用提案：重新鉴权 + revision guard + 乐观锁 + 执行 + 审计。"""
    proposal = db.get(V3ActionProposal, proposal_id)
    if not proposal or proposal.project_id != project_id:
        raise ProposalError("提案不存在")
    # 重新鉴权：操作者必须是提案所有者
    if proposal.owner_id != user_id:
        raise ProposalError("无权操作该提案")
    if proposal.status != "pending":
        raise ProposalError(f"提案状态 {proposal.status} 不可应用")

    # revision guard：base revision 过期则拒绝并要求重新生成
    current_hash = context_selector.compute_revision_hash(db, project_id)
    if proposal.base_revision_hash != current_hash:
        proposal.status = "expired"
        db.commit()
        raise ProposalExpiredError("项目版本已变更，提案过期，请重新生成")

    # 乐观锁：目标资产 lock_version 与提案创建时一致才可应用
    spec = ACTION_TYPES.get(proposal.action_type)
    if spec is None:
        raise ProposalError(f"未定义操作类型：{proposal.action_type}")
    target = _resolve_target(db, project_id, proposal.target_type, proposal.target_ref)
    if target is None:
        raise ProposalError("目标资产已不存在")
    target_lock = getattr(target, "lock_version", 0)
    if target_lock != proposal.target_lock_version:
        raise ProposalExpiredError("目标资产已被其他人修改（乐观锁冲突），请重新生成提案")

    # 执行变更
    try:
        _apply_changes(db, proposal, target, spec)
    except ProposalError:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        proposal.apply_error = str(exc)[:4000]
        db.commit()
        raise ProposalError(f"提案应用失败：{exc}") from exc

    proposal.status = "applied"
    proposal.applied_by = user_id
    proposal.applied_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(AuditLog(
        user_id=user_id,
        action="v3.proposal.apply",
        target_type="v3_action_proposal",
        target_id=proposal.id,
        detail=f"action={proposal.action_type};target={proposal.target_type}:{proposal.target_ref}",
    ))
    db.commit()
    db.refresh(proposal)
    return proposal


def _apply_changes(db: Session, proposal: V3ActionProposal, target, spec: dict[str, Any]) -> None:
    """按操作类型执行结构化 diff。所有字段写前校验。"""
    allowed_fields: set[str] = spec["fields"]

    if proposal.action_type == "update_anchor_controllable_vars":
        controllable = dict(target.controllable_vars or {})
        for change in proposal.changes:
            field = str(change.get("field", ""))
            if field not in allowed_fields:
                raise ProposalError(f"提案试图修改未授权字段：{field}")
            controllable[field] = str(change.get("after", ""))[:2000]
        # 身份锚点字段绝不触碰（白名单保证 + 双重保险）
        target.controllable_vars = controllable
        target.lock_version = target.lock_version + 1
        db.flush()
        return

    if proposal.action_type == "suggest_prop_state":
        for change in proposal.changes:
            field = str(change.get("field", ""))
            if field == "wear_condition":
                target.wear_condition = str(change.get("after", ""))[:2000]
            elif field == "state_change":
                states = list(target.state_changes or [])
                states.append({"change": str(change.get("after", ""))[:1000]})
                target.state_changes = states
            else:
                raise ProposalError(f"提案试图修改未授权字段：{field}")
        target.lock_version = target.lock_version + 1
        db.flush()
        return

    if proposal.action_type == "suggest_continuity_resolution":
        # 场景级处理说明记录在提案本身（resolution 语义），不改场景数据
        for change in proposal.changes:
            field = str(change.get("field", ""))
            if field not in allowed_fields:
                raise ProposalError(f"提案试图修改未授权字段：{field}")
        proposal.rationale = str(proposal.changes[0].get("after", ""))[:2000] if proposal.changes else proposal.rationale
        return

    raise ProposalError(f"操作类型 {proposal.action_type} 没有实现执行器")


def dismiss_proposal(db: Session, user_id: int, project_id: int, proposal_id: int, reason: str) -> V3ActionProposal:
    """忽略提案（记录原因）。"""
    proposal = db.get(V3ActionProposal, proposal_id)
    if not proposal or proposal.project_id != project_id:
        raise ProposalError("提案不存在")
    if proposal.owner_id != user_id:
        raise ProposalError("无权操作该提案")
    if proposal.status != "pending":
        raise ProposalError(f"提案状态 {proposal.status} 不可忽略")
    proposal.status = "dismissed"
    proposal.dismissed_reason = reason[:2000]
    db.commit()
    db.refresh(proposal)
    return proposal


def list_proposals(
    db: Session,
    owner_id: int,
    project_id: int,
    status: str | None = None,
) -> list[V3ActionProposal]:
    q = db.query(V3ActionProposal).filter(
        V3ActionProposal.project_id == project_id,
        V3ActionProposal.owner_id == owner_id,
    )
    if status:
        q = q.filter(V3ActionProposal.status == status)
    return q.order_by(V3ActionProposal.id.desc()).limit(100).all()


def mark_expired_proposals(db: Session, project_id: int) -> int:
    """把 base revision 已过期的 pending 提案标记为 expired（revision guard 的批处理形式）。"""
    current_hash = context_selector.compute_revision_hash(db, project_id)
    rows = db.query(V3ActionProposal).filter(
        V3ActionProposal.project_id == project_id,
        V3ActionProposal.status == "pending",
        V3ActionProposal.base_revision_hash != current_hash,
    ).all()
    for p in rows:
        p.status = "expired"
    db.commit()
    return len(rows)


def proposal_out(db: Session, p: V3ActionProposal) -> dict[str, Any]:
    current_hash = context_selector.compute_revision_hash(db, p.project_id)
    return {
        "id": p.id,
        "project_id": p.project_id,
        "action_type": p.action_type,
        "action_desc": ACTION_TYPES.get(p.action_type, {}).get("desc", p.action_type),
        "target_type": p.target_type,
        "target_ref": p.target_ref,
        "target_lock_version": p.target_lock_version,
        "base_revision_hash": p.base_revision_hash,
        "revision_current": p.base_revision_hash == current_hash,
        "title": p.title,
        "rationale": p.rationale,
        "changes": p.changes,
        "impact_refs": p.impact_refs,
        "status": p.status,
        "applied_at": p.applied_at,
        "apply_error": p.apply_error,
        "dismissed_reason": p.dismissed_reason,
        "created_at": p.created_at,
    }
