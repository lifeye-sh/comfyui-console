"""统一审批服务：候选、批准、拒绝、从批准版本派生新候选。

契约见 docs/v3-director-rfc.md §3。已批准版本不可原地修改；修改必须产生新候选。
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.v3_director import V3ApprovalDecision

_VALID_STATUSES = {"draft", "candidate", "approved", "rejected", "waived"}


def submit_candidate(
    db: Session,
    project_id: int,
    owner_id: int | None,
    target_type: str,
    target_ref: str,
    payload: dict | None = None,
    validation_errors: list | None = None,
    parent_approved_id: int | None = None,
) -> V3ApprovalDecision:
    """提交一个待审批候选。"""
    decision = V3ApprovalDecision(
        project_id=project_id,
        owner_id=owner_id,
        target_type=target_type,
        target_ref=target_ref,
        status="candidate",
        payload=payload or {},
        validation_errors=validation_errors or [],
        parent_approved_id=parent_approved_id,
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return decision


def approve(
    db: Session,
    approval_id: int,
    decided_by: int,
    reason: str | None = None,
) -> V3ApprovalDecision:
    """批准候选。已批准/已拒绝/已豁免的不可重复决策。"""
    d = db.get(V3ApprovalDecision, approval_id)
    if not d:
        raise ValueError("审批记录不存在")
    if d.status != "candidate":
        raise ValueError(f"当前状态 {d.status} 不可批准")
    d.status = "approved"
    d.decided_by = decided_by
    d.decided_at = datetime.now(timezone.utc)
    d.decision_reason = reason
    db.commit()
    db.refresh(d)
    return d


def reject(
    db: Session,
    approval_id: int,
    decided_by: int,
    reason: str,
) -> V3ApprovalDecision:
    """拒绝候选（必须给理由）。"""
    d = db.get(V3ApprovalDecision, approval_id)
    if not d:
        raise ValueError("审批记录不存在")
    if d.status != "candidate":
        raise ValueError(f"当前状态 {d.status} 不可拒绝")
    if not reason or not reason.strip():
        raise ValueError("拒绝必须提供理由")
    d.status = "rejected"
    d.decided_by = decided_by
    d.decided_at = datetime.now(timezone.utc)
    d.decision_reason = reason
    db.commit()
    db.refresh(d)
    return d


def waive(
    db: Session,
    approval_id: int,
    decided_by: int,
    reason: str,
) -> V3ApprovalDecision:
    """豁免（仅用于 blocker 降级，需审批人和原因）。"""
    d = db.get(V3ApprovalDecision, approval_id)
    if not d:
        raise ValueError("审批记录不存在")
    if d.status != "candidate":
        raise ValueError(f"当前状态 {d.status} 不可豁免")
    if not reason or not reason.strip():
        raise ValueError("豁免必须提供原因")
    d.status = "waived"
    d.decided_by = decided_by
    d.decided_at = datetime.now(timezone.utc)
    d.decision_reason = reason
    db.commit()
    db.refresh(d)
    return d


def derive_candidate(
    db: Session,
    parent_approved_id: int,
    payload: dict,
    validation_errors: list | None = None,
) -> V3ApprovalDecision:
    """从已批准版本派生新候选（修改批准版本的唯一方式）。"""
    parent = db.get(V3ApprovalDecision, parent_approved_id)
    if not parent:
        raise ValueError("父审批记录不存在")
    if parent.status != "approved":
        raise ValueError("只能从已批准的版本派生新候选")
    return submit_candidate(
        db,
        project_id=parent.project_id,
        owner_id=parent.owner_id,
        target_type=parent.target_type,
        target_ref=parent.target_ref,
        payload=payload,
        validation_errors=validation_errors,
        parent_approved_id=parent.id,
    )


def get_approved_version(
    db: Session,
    project_id: int,
    target_type: str,
    target_ref: str,
) -> V3ApprovalDecision | None:
    """获取该目标当前已批准的最新版本。"""
    return (
        db.query(V3ApprovalDecision)
        .filter(
            V3ApprovalDecision.project_id == project_id,
            V3ApprovalDecision.target_type == target_type,
            V3ApprovalDecision.target_ref == target_ref,
            V3ApprovalDecision.status == "approved",
        )
        .order_by(V3ApprovalDecision.id.desc())
        .first()
    )


def list_approvals(
    db: Session,
    project_id: int,
    target_type: str | None = None,
    status: str | None = None,
) -> list[V3ApprovalDecision]:
    q = db.query(V3ApprovalDecision).filter(V3ApprovalDecision.project_id == project_id)
    if target_type:
        q = q.filter(V3ApprovalDecision.target_type == target_type)
    if status:
        if status not in _VALID_STATUSES:
            raise ValueError("无效审批状态")
        q = q.filter(V3ApprovalDecision.status == status)
    return q.order_by(V3ApprovalDecision.id.desc()).all()
