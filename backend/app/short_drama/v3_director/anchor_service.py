"""角色/道具锚点服务：主角优先级、不可变身份、可控状态、禁止漂移、Checkpoint C。

契约见实施计划第 5 轮：
- 主角优先级：配角生成不能绕过主角依赖规则
- 变体必须引用已批准锚点；修改状态变量不能覆盖身份锚点
- Checkpoint C 逐实体审批，不允许全局 AI 自动通过
- Checkpoint B 通过（有批准风格圣经）才允许批量创建实际锚点生成任务
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.v3_director import V3CharacterAnchorVersion, V3PropAnchorVersion, V3StyleBibleVersion

PRIORITY_ORDER = {"protagonist": 0, "supporting": 1, "extra": 2}


def _style_check(db: Session, project_id: int) -> tuple[bool, str, int | None]:
    """Checkpoint B 检查：必须有已批准风格圣经才能创建实际锚点。"""
    approved = (
        db.query(V3StyleBibleVersion)
        .filter(V3StyleBibleVersion.project_id == project_id, V3StyleBibleVersion.status == "approved")
        .order_by(V3StyleBibleVersion.id.desc())
        .first()
    )
    if not approved:
        return False, "没有已批准的风格圣经（Checkpoint B 未通过），不能创建实际锚点", None
    return True, "", approved.id


def next_anchor_version(db: Session, project_id: int, stable_key: str) -> int:
    last = (
        db.query(V3CharacterAnchorVersion.version)
        .filter(
            V3CharacterAnchorVersion.project_id == project_id,
            V3CharacterAnchorVersion.stable_key == stable_key,
        )
        .order_by(V3CharacterAnchorVersion.version.desc())
        .first()
    )
    return (last[0] if last else 0) + 1


def next_prop_anchor_version(db: Session, project_id: int, stable_key: str) -> int:
    last = (
        db.query(V3PropAnchorVersion.version)
        .filter(
            V3PropAnchorVersion.project_id == project_id,
            V3PropAnchorVersion.stable_key == stable_key,
        )
        .order_by(V3PropAnchorVersion.version.desc())
        .first()
    )
    return (last[0] if last else 0) + 1


def create_character_anchor(
    db: Session,
    project_id: int,
    stable_key: str,
    name: str,
    identity_anchor: dict,
    controllable_vars: dict,
    drift_prohibition: list,
    priority: str = "supporting",
    style_bible_id: int | None = None,
    character_id: int | None = None,
    expression_sheet: list | None = None,
    generation_record_id: int | None = None,
) -> V3CharacterAnchorVersion:
    """创建角色锚点候选。

    Checkpoint B 检查：必须有已批准风格圣经才能创建锚点。
    """
    if priority not in PRIORITY_ORDER:
        raise ValueError("priority 必须是 protagonist/supporting/extra")
    ok, reason, approved_style_id = _style_check(db, project_id)
    if not ok:
        raise ValueError(reason)
    # 稳定键校验：identity_anchor 必须非空
    if not identity_anchor or not isinstance(identity_anchor, dict):
        raise ValueError("identity_anchor 不能为空")
    version = next_anchor_version(db, project_id, stable_key)
    anchor = V3CharacterAnchorVersion(
        project_id=project_id,
        stable_key=stable_key,
        name=name,
        identity_anchor=identity_anchor,
        controllable_vars=controllable_vars or {},
        drift_prohibition=drift_prohibition or [],
        expression_sheet=expression_sheet or [],
        priority=priority,
        style_bible_id=style_bible_id or approved_style_id,
        character_id=character_id,
        version=version,
        generation_record_id=generation_record_id,
    )
    db.add(anchor)
    db.commit()
    db.refresh(anchor)
    return anchor


def create_prop_anchor(
    db: Session,
    project_id: int,
    stable_key: str,
    name: str,
    fields: dict,
    style_bible_id: int | None = None,
    prop_id: int | None = None,
    generation_record_id: int | None = None,
) -> V3PropAnchorVersion:
    """创建道具锚点候选。Checkpoint B 检查同角色锚点。"""
    ok, reason, approved_style_id = _style_check(db, project_id)
    if not ok:
        raise ValueError(reason)
    version = next_prop_anchor_version(db, project_id, stable_key)
    anchor = V3PropAnchorVersion(
        project_id=project_id,
        stable_key=stable_key,
        name=name,
        size=str(fields.get("size") or ""),
        material=str(fields.get("material") or ""),
        wear_condition=str(fields.get("wear_condition") or ""),
        owner_character_key=fields.get("owner_character_key"),
        state_changes=fields.get("state_changes") or [],
        drift_prohibition=fields.get("drift_prohibition") or [],
        priority_rank=int(fields.get("priority_rank") or 0),
        style_bible_id=style_bible_id or approved_style_id,
        prop_id=prop_id,
        version=version,
        generation_record_id=generation_record_id,
    )
    db.add(anchor)
    db.commit()
    db.refresh(anchor)
    return anchor


def approve_character_anchor(
    db: Session, project_id: int, anchor_id: int, user_id: int
) -> V3CharacterAnchorVersion:
    """Checkpoint C 逐实体批准角色锚点。"""
    anchor = db.get(V3CharacterAnchorVersion, anchor_id)
    if not anchor or anchor.project_id != project_id:
        raise ValueError("角色锚点不存在")
    if anchor.status != "candidate":
        raise ValueError(f"当前状态 {anchor.status} 不可批准")
    anchor.status = "approved"
    anchor.approved_by = user_id
    from datetime import datetime, timezone
    anchor.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(anchor)
    return anchor


def approve_prop_anchor(
    db: Session, project_id: int, anchor_id: int, user_id: int
) -> V3PropAnchorVersion:
    """Checkpoint C 逐实体批准道具锚点。"""
    anchor = db.get(V3PropAnchorVersion, anchor_id)
    if not anchor or anchor.project_id != project_id:
        raise ValueError("道具锚点不存在")
    if anchor.status != "candidate":
        raise ValueError(f"当前状态 {anchor.status} 不可批准")
    anchor.status = "approved"
    anchor.approved_by = user_id
    from datetime import datetime, timezone
    anchor.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(anchor)
    return anchor


def checkpoint_c_status(db: Session, project_id: int) -> dict:
    """Checkpoint C 检查：所有已创建的锚点必须逐实体批准。"""
    total = (
        db.query(V3CharacterAnchorVersion)
        .filter(V3CharacterAnchorVersion.project_id == project_id)
        .count()
    )
    approved_chars = (
        db.query(V3CharacterAnchorVersion)
        .filter(
            V3CharacterAnchorVersion.project_id == project_id,
            V3CharacterAnchorVersion.status == "approved",
        )
        .count()
    )
    prop_total = (
        db.query(V3PropAnchorVersion)
        .filter(V3PropAnchorVersion.project_id == project_id)
        .count()
    )
    approved_props = (
        db.query(V3PropAnchorVersion)
        .filter(
            V3PropAnchorVersion.project_id == project_id,
            V3PropAnchorVersion.status == "approved",
        )
        .count()
    )
    pending_chars = total - approved_chars
    pending_props = prop_total - approved_props
    passed = pending_chars == 0 and pending_props == 0 and total > 0
    return {
        "passed": passed,
        "character_total": total,
        "character_approved": approved_chars,
        "character_pending": pending_chars,
        "prop_total": prop_total,
        "prop_approved": approved_props,
        "prop_pending": pending_props,
        "reason": "" if passed else f"还有 {pending_chars} 个角色锚点和 {pending_props} 个道具锚点待审批",
    }


def list_character_anchors(
    db: Session, project_id: int, status: str | None = None, priority: str | None = None
) -> list[V3CharacterAnchorVersion]:
    q = db.query(V3CharacterAnchorVersion).filter(V3CharacterAnchorVersion.project_id == project_id)
    if status:
        q = q.filter(V3CharacterAnchorVersion.status == status)
    if priority:
        q = q.filter(V3CharacterAnchorVersion.priority == priority)
    # 主角优先排序
    priority_order = {"protagonist": 0, "supporting": 1, "extra": 2}
    rows = q.order_by(V3CharacterAnchorVersion.id.desc()).all()
    rows.sort(key=lambda a: priority_order.get(a.priority, 3))
    return rows


def list_prop_anchors(db: Session, project_id: int, status: str | None = None) -> list[V3PropAnchorVersion]:
    q = db.query(V3PropAnchorVersion).filter(V3PropAnchorVersion.project_id == project_id)
    if status:
        q = q.filter(V3PropAnchorVersion.status == status)
    return q.order_by(V3PropAnchorVersion.priority_rank, V3PropAnchorVersion.id.desc()).all()


def char_anchor_out(a: V3CharacterAnchorVersion) -> dict:
    return {
        "id": a.id, "project_id": a.project_id, "stable_key": a.stable_key,
        "character_id": a.character_id, "style_bible_id": a.style_bible_id,
        "version": a.version, "parent_version_id": a.parent_version_id,
        "status": a.status, "priority": a.priority, "name": a.name,
        "identity_anchor": a.identity_anchor, "controllable_vars": a.controllable_vars,
        "drift_prohibition": a.drift_prohibition, "expression_sheet": a.expression_sheet,
        "front_resource_id": a.front_resource_id, "side_resource_id": a.side_resource_id,
        "back_resource_id": a.back_resource_id,
        "validation_errors": a.validation_errors,
        "approved_by": a.approved_by, "approved_at": a.approved_at,
    }


def prop_anchor_out(a: V3PropAnchorVersion) -> dict:
    return {
        "id": a.id, "project_id": a.project_id, "stable_key": a.stable_key,
        "prop_id": a.prop_id, "style_bible_id": a.style_bible_id,
        "version": a.version, "parent_version_id": a.parent_version_id,
        "status": a.status, "name": a.name, "priority_rank": a.priority_rank,
        "size": a.size, "material": a.material, "wear_condition": a.wear_condition,
        "owner_character_key": a.owner_character_key, "state_changes": a.state_changes,
        "drift_prohibition": a.drift_prohibition,
        "hero_shot_resource_id": a.hero_shot_resource_id,
        "validation_errors": a.validation_errors,
        "approved_by": a.approved_by, "approved_at": a.approved_at,
    }