"""稳定键服务：分配、沿用、退役。契约见 docs/v3-director-rfc.md §2。

规则：
- 键在同一 (project_id, entity_type) 内唯一。
- 已退役键不得复用。
- 键不依赖数据库主键。
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.v3_director import V3StableIdentity

# 实体类型前缀（与 RFC §2.1 一致）
_TYPE_PREFIXES: dict[str, str] = {
    "scene": "SC",
    "beat": "BT",
    "character": "CH",
    "character_state": "CH",
    "location": "LOC",
    "location_view": "LOC",
    "prop": "PR",
    "style": "STYLE",
    "palette": "PAL",
    "spatial_plan": "SPL",
}


def _prefix(entity_type: str) -> str:
    return _TYPE_PREFIXES.get(entity_type, entity_type[:3].upper())


def _format_key(prefix: str, seq: int) -> str:
    if prefix in ("STYLE", "PAL"):
        return f"{prefix}-v{seq:02d}"
    return f"{prefix}-{seq:03d}"


def allocate(
    db: Session,
    project_id: int,
    entity_type: str,
    owner_id: int | None = None,
    created_from_type: str | None = None,
    created_from_id: int | None = None,
) -> V3StableIdentity:
    """分配下一个可用稳定键（扫描当前最大序号 + 1；已退役键不复用但序号不重排）。"""
    prefix = _prefix(entity_type)
    # 找当前项目该类型下所有键，解析最大序号
    rows = db.query(V3StableIdentity.stable_key).filter(
        V3StableIdentity.project_id == project_id,
        V3StableIdentity.entity_type == entity_type,
    ).all()
    max_seq = 0
    for (key,) in rows:
        # 解析 "SC-001" 或 "STYLE-v01"
        try:
            num_part = key.rsplit("-", 1)[-1].lstrip("v")
            seq = int(num_part)
            max_seq = max(max_seq, seq)
        except (ValueError, IndexError):
            continue
    next_seq = max_seq + 1
    identity = V3StableIdentity(
        project_id=project_id,
        entity_type=entity_type,
        stable_key=_format_key(prefix, next_seq),
        status="active",
        created_from_type=created_from_type,
        created_from_id=created_from_id,
    )
    db.add(identity)
    db.commit()
    db.refresh(identity)
    return identity


def retire(db: Session, identity_id: int, reason: str | None = None) -> V3StableIdentity:
    """退役稳定键（不复用、不重排）。"""
    identity = db.get(V3StableIdentity, identity_id)
    if not identity:
        raise ValueError("稳定键不存在")
    if identity.status == "retired":
        raise ValueError("稳定键已退役")
    identity.status = "retired"
    identity.retired_at = datetime.now(timezone.utc)
    identity.retired_reason = reason
    db.commit()
    db.refresh(identity)
    return identity


def resolve(
    db: Session,
    project_id: int,
    entity_type: str,
    stable_key: str,
    *,
    require_active: bool = True,
) -> V3StableIdentity | None:
    """按业务键查找；require_active=True 时退役键返回 None。"""
    q = db.query(V3StableIdentity).filter(
        V3StableIdentity.project_id == project_id,
        V3StableIdentity.entity_type == entity_type,
        V3StableIdentity.stable_key == stable_key,
    )
    if require_active:
        q = q.filter(V3StableIdentity.status == "active")
    return q.first()


def list_by_project(
    db: Session,
    project_id: int,
    entity_type: str | None = None,
    include_retired: bool = False,
) -> list[V3StableIdentity]:
    q = db.query(V3StableIdentity).filter(V3StableIdentity.project_id == project_id)
    if entity_type:
        q = q.filter(V3StableIdentity.entity_type == entity_type)
    if not include_retired:
        q = q.filter(V3StableIdentity.status == "active")
    return q.order_by(V3StableIdentity.entity_type, V3StableIdentity.stable_key).all()
