"""空间资产服务：外景拓扑/内景平面图（先结构版本）→ 关键视图（后视图版本）。

契约见实施计划第 6 轮：
- LocationViewVersion 必须引用批准或选定的 SpatialPlanVersion
- 视图不能反向覆盖空间结构
- 空间版本更新后，旧关键视图被准确标记 stale
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.v3_director import V3LocationViewVersion, V3SpatialPlanVersion


def _validate_plan_payload(kind: str, payload: dict) -> list[dict]:
    """校验拓扑/平面图 JSON Schema：单位、坐标系、必要锚点。"""
    errors: list[dict] = []
    if kind not in ("exterior", "interior"):
        errors.append({"field": "plan_kind", "message": "plan_kind 必须是 exterior 或 interior"})
    if kind == "exterior":
        topo = payload.get("topology") or {}
        if not topo.get("landmarks"):
            errors.append({"field": "topology.landmarks", "message": "外景拓扑必须包含至少一个地标"})
    elif kind == "interior":
        fp = payload.get("floor_plan") or {}
        if not fp.get("scale"):
            errors.append({"field": "floor_plan.scale", "message": "内景平面图必须包含比例（scale）"})
        if not fp.get("doors"):
            errors.append({"field": "floor_plan.doors", "message": "内景平面图必须包含门窗定义"})
    return errors


def next_plan_version(db: Session, project_id: int, location_stable_key: str) -> int:
    last = (
        db.query(V3SpatialPlanVersion.version)
        .filter(
            V3SpatialPlanVersion.project_id == project_id,
            V3SpatialPlanVersion.location_stable_key == location_stable_key,
        )
        .order_by(V3SpatialPlanVersion.version.desc())
        .first()
    )
    return (last[0] if last else 0) + 1


def create_plan(
    db: Session,
    project_id: int,
    location_stable_key: str,
    plan_kind: str,
    name: str,
    topology: dict | None = None,
    floor_plan: dict | None = None,
    scale: str = "",
    location_id: int | None = None,
    parent_version_id: int | None = None,
    provenance: dict | None = None,
) -> tuple[V3SpatialPlanVersion, list[dict]]:
    """创建空间结构版本候选。返回 (plan, validation_errors)。"""
    payload = {"topology": topology or {}, "floor_plan": floor_plan or {}}
    errors = _validate_plan_payload(plan_kind, payload)
    version = (
        db.query(V3SpatialPlanVersion.version)
        .filter(
            V3SpatialPlanVersion.project_id == project_id,
            V3SpatialPlanVersion.location_stable_key == location_stable_key,
        )
        .order_by(V3SpatialPlanVersion.version.desc())
        .first()
    )
    plan = V3SpatialPlanVersion(
        project_id=project_id,
        location_stable_key=location_stable_key,
        location_id=location_id,
        plan_kind=plan_kind,
        version=(version[0] if version else 0) + 1,
        parent_version_id=parent_version_id,
        status="invalid" if errors else "candidate",
        name=name,
        scale=str((floor_plan or {}).get("scale") or ""),
        topology=topology or {},
        floor_plan=floor_plan or {},
        validation_errors=errors,
        provenance=provenance or {},
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan, errors


def get_plan(db: Session, project_id: int, plan_id: int) -> V3SpatialPlanVersion | None:
    return db.query(V3SpatialPlanVersion).filter(
        V3SpatialPlanVersion.id == plan_id,
        V3SpatialPlanVersion.project_id == project_id,
    ).first()


def approve_plan(db: Session, project_id: int, plan_id: int, user_id: int) -> V3SpatialPlanVersion:
    plan = db.get(V3SpatialPlanVersion, plan_id)
    if not plan or plan.project_id != project_id:
        raise ValueError("空间结构版本不存在")
    if plan.status != "candidate":
        raise ValueError(f"当前状态 {plan.status} 不可批准")
    plan.status = "approved"
    plan.approved_by = user_id
    from datetime import datetime, timezone
    plan.approved_at = datetime.now(timezone.utc)
    # 空间版本批准后，旧关键视图标记 stale
    old_views = (
        db.query(V3LocationViewVersion)
        .filter(
            V3LocationViewVersion.project_id == project_id,
            V3LocationViewVersion.stable_key.like(f"{plan.location_stable_key}-%"),
            V3LocationViewVersion.status == "approved",
            V3LocationViewVersion.spatial_plan_id != plan.id,
        )
        .all()
    )
    for view in old_views:
        view.status = "stale"
    db.commit()
    db.refresh(plan)
    return plan


def next_view_version(db: Session, project_id: int, location_stable_key: str) -> int:
    prefix = f"{location_stable_key}-V"
    rows = (
        db.query(V3LocationViewVersion.stable_key)
        .filter(V3LocationViewVersion.project_id == project_id)
        .all()
    )
    max_seq = 0
    for (key,) in rows:
        if key.startswith(prefix):
            try:
                max_seq = max(max_seq, int(key[len(prefix):]))
            except ValueError:
                continue
    return max_seq + 1


def create_view(
    db: Session,
    project_id: int,
    spatial_plan_id: int,
    name: str,
    description: str,
    view_angle: str = "",
    resource_id: int | None = None,
    provenance: dict | None = None,
) -> V3LocationViewVersion:
    """创建关键视图。空间结构必须是 candidate 或 approved（不能是 invalid/retired）。"""
    plan = db.get(V3SpatialPlanVersion, spatial_plan_id)
    if not plan or plan.project_id != project_id:
        raise ValueError("空间结构版本不存在")
    if plan.status not in ("candidate", "approved"):
        raise ValueError(f"空间结构状态 {plan.status} 不允许创建视图")
    seq = next_view_version(db, project_id, plan.location_stable_key)
    view = V3LocationViewVersion(
        project_id=project_id,
        spatial_plan_id=spatial_plan_id,
        stable_key=f"{plan.location_stable_key}-V{seq:02d}",
        version=seq,
        name=name,
        description=description,
        view_angle=view_angle,
        resource_id=resource_id,
        provenance=provenance or {},
    )
    db.add(view)
    db.commit()
    db.refresh(view)
    return view


def approve_view(db: Session, project_id: int, view_id: int, user_id: int) -> V3LocationViewVersion:
    view = db.get(V3LocationViewVersion, view_id)
    if not view or view.project_id != project_id:
        raise ValueError("关键视图不存在")
    if view.status != "candidate":
        raise ValueError(f"当前状态 {view.status} 不可批准")
    view.status = "approved"
    view.approved_by = user_id
    from datetime import datetime, timezone
    view.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(view)
    return view


def list_plans(db: Session, project_id: int) -> list[V3SpatialPlanVersion]:
    return (
        db.query(V3SpatialPlanVersion)
        .filter(V3SpatialPlanVersion.project_id == project_id)
        .order_by(V3SpatialPlanVersion.location_stable_key, V3SpatialPlanVersion.version.desc())
        .all()
    )


def list_views(db: Session, project_id: int, spatial_plan_id: int | None = None) -> list[V3LocationViewVersion]:
    q = db.query(V3LocationViewVersion).filter(V3LocationViewVersion.project_id == project_id)
    if spatial_plan_id:
        q = q.filter(V3LocationViewVersion.spatial_plan_id == spatial_plan_id)
    return q.order_by(V3LocationViewVersion.stable_key, V3LocationViewVersion.version.desc()).all()


def plan_out(plan: V3SpatialPlanVersion) -> dict:
    return {
        "id": plan.id, "project_id": plan.project_id,
        "location_stable_key": plan.location_stable_key, "location_id": plan.location_id,
        "plan_kind": plan.plan_kind, "version": plan.version,
        "parent_version_id": plan.parent_version_id, "status": plan.status,
        "name": plan.name, "scale": plan.scale,
        "topology": plan.topology, "floor_plan": plan.floor_plan,
        "validation_errors": plan.validation_errors,
        "approved_by": plan.approved_by, "approved_at": plan.approved_at,
    }


def view_out(view: V3LocationViewVersion) -> dict:
    return {
        "id": view.id, "project_id": view.project_id,
        "spatial_plan_id": view.spatial_plan_id, "stable_key": view.stable_key,
        "version": view.version, "parent_version_id": view.parent_version_id,
        "status": view.status, "name": view.name, "description": view.description,
        "view_angle": view.view_angle, "resource_id": view.resource_id,
        "created_at": view.created_at,
    }
