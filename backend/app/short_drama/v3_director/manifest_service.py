"""Manifest 服务：从已批准资产自动生成清单、依赖图建立、状态操作。

契约见实施计划第 7 轮：
- 每个 Item 引用真实版本外键和稳定键
- 上游变化只影响有依赖边的下游资产
- 已批准 Manifest 不可原地修改
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.v3_director import (
    V3ArtifactDependency,
    V3CharacterAnchorVersion,
    V3GenerationManifest,
    V3LocationViewVersion,
    V3ManifestItem,
    V3ManifestReference,
    V3PropAnchorVersion,
    V3StaleRecord,
    V3StyleBibleVersion,
)


# --------------------------------------------------------------------------- #
# 依赖图
# --------------------------------------------------------------------------- #

def build_dependency_graph(db: Session, project_id: int) -> int:
    """确定性规则建立 ArtifactDependency 边。

    规则：
    - character_anchor → style_bible（identity 依赖）
    - prop_anchor → style_bible（style 依赖）
    - prop_anchor → character_anchor（wardrobe 依赖，若 owner_character_key 存在）
    - location_view → spatial_plan（spatial 依赖）
    """
    from app.models import (
        V3CharacterAnchorVersion as CA, V3PropAnchorVersion as PA, V3LocationViewVersion as LV,
    )

    # 清理旧边（保留历史记录在 stale_records 中）
    db.query(V3ArtifactDependency).filter(
        V3ArtifactDependency.project_id == project_id
    ).delete()

    count = 0
    for a in db.query(CA).filter(CA.project_id == project_id).all():
        if a.style_bible_id:
            db.add(V3ArtifactDependency(
                project_id=project_id,
                downstream_type="character_anchor", downstream_ref=a.stable_key,
                upstream_type="style_bible", upstream_ref=f"STYLE-v{a.style_bible_id}",
                dependency_type="style",
            ))
            count += 1
    for a in db.query(PA).filter(PA.project_id == project_id).all():
        if a.style_bible_id:
            db.add(V3ArtifactDependency(
                project_id=project_id,
                downstream_type="prop_anchor", downstream_ref=a.stable_key,
                upstream_type="style_bible", upstream_ref=f"STYLE-v{a.style_bible_id}",
                dependency_type="style",
            ))
            count += 1
        if a.owner_character_key:
            db.add(V3ArtifactDependency(
                project_id=project_id,
                downstream_type="prop_anchor", downstream_ref=a.stable_key,
                upstream_type="character_anchor", upstream_ref=a.owner_character_key,
                dependency_type="wardrobe",
            ))
            count += 1
    for v in db.query(LV).filter(LV.project_id == project_id).all():
        db.add(V3ArtifactDependency(
            project_id=project_id,
            downstream_type="location_view", downstream_ref=v.stable_key,
            upstream_type="spatial_plan", upstream_ref=f"SPL-{v.spatial_plan_id}",
            dependency_type="spatial",
        ))
        count += 1
    db.commit()
    return count


def list_dependencies(db: Session, project_id: int) -> list[V3ArtifactDependency]:
    return db.query(V3ArtifactDependency).filter(
        V3ArtifactDependency.project_id == project_id
    ).order_by(V3ArtifactDependency.id).all()


def dependency_out(d: V3ArtifactDependency) -> dict:
    return {
        "id": d.id,
        "downstream_type": d.downstream_type,
        "downstream_ref": d.downstream_ref,
        "upstream_type": d.upstream_type,
        "upstream_ref": d.upstream_ref,
        "dependency_type": d.dependency_type,
        "created_at": d.created_at,
    }


# --------------------------------------------------------------------------- #
# Stale 传播
# --------------------------------------------------------------------------- #

def propagate_stale(db: Session, project_id: int, upstream_type: str, upstream_ref: str, reason: str) -> int:
    """上游变更后，沿依赖边传递标记下游资产过期。"""
    deps = db.query(V3ArtifactDependency).filter(
        V3ArtifactDependency.project_id == project_id,
        V3ArtifactDependency.upstream_type == upstream_type,
        V3ArtifactDependency.upstream_ref == upstream_ref,
    ).all()
    count = 0
    for dep in deps:
        exists = db.query(V3StaleRecord).filter(
            V3StaleRecord.project_id == project_id,
            V3StaleRecord.asset_type == dep.downstream_type,
            V3StaleRecord.asset_ref == dep.downstream_ref,
            V3StaleRecord.status == "open",
        ).first()
        if exists:
            continue
        db.add(V3StaleRecord(
            project_id=project_id,
            asset_type=dep.downstream_type,
            asset_ref=dep.downstream_ref,
            stale_reason=reason,
            detail=f"上游 {upstream_ref} 变更",
            source_dependency_id=dep.id,
        ))
        count += 1
    db.commit()
    return count


def list_stale_records(db: Session, project_id: int, status: str | None = None) -> list[V3StaleRecord]:
    q = db.query(V3StaleRecord).filter(V3StaleRecord.project_id == project_id)
    if status:
        q = q.filter(V3StaleRecord.status == status)
    return q.order_by(V3StaleRecord.id.desc()).all()


def resolve_stale(db: Session, stale_id: int, user_id: int, resolution: str = "") -> V3StaleRecord:
    rec = db.get(V3StaleRecord, stale_id)
    if not rec:
        raise ValueError("过期记录不存在")
    if rec.status != "open":
        raise ValueError("记录已处理")
    rec.status = "resolved"
    rec.resolved_by = user_id
    rec.resolution = resolution
    db.commit()
    db.refresh(rec)
    return rec


def stale_out(r: V3StaleRecord) -> dict:
    return {
        "id": r.id, "project_id": r.project_id,
        "asset_type": r.asset_type, "asset_ref": r.asset_ref,
        "stale_reason": r.stale_reason, "detail": r.detail,
        "source_dependency_id": r.source_dependency_id,
        "status": r.status, "resolution": r.resolution,
        "created_at": r.created_at,
    }


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #

def next_manifest_version(db: Session, project_id: int) -> int:
    last = (
        db.query(V3GenerationManifest.version)
        .filter(V3GenerationManifest.project_id == project_id)
        .order_by(V3GenerationManifest.version.desc())
        .first()
    )
    return (last[0] if last else 0) + 1


_IDENTITY_LABELS = {
    "story_profile": "故事人物特征",
    "appearance": "外貌",
    "age_range": "年龄段",
    "personality": "性格",
    "feature_marks": "特征标记",
    "face_ratios": "面部比例",
}


def _identity_text(identity: dict) -> str:
    """把身份锚点 dict 展开成可读中文文本，供形象生成 prompt 使用。"""
    if not isinstance(identity, dict):
        return str(identity or "无")
    parts: list[str] = []
    for key, label in _IDENTITY_LABELS.items():
        value = identity.get(key)
        if value and str(value).strip():
            parts.append(f"{label}：{value}")
    if parts:
        return "；".join(parts)
    # 未知字段兜底
    extra = [f"{k}：{v}" for k, v in identity.items() if v and str(v).strip()]
    return "；".join(extra) if extra else "无"


def build_manifest_from_approved(db: Session, project_id: int, notes: str = "") -> V3GenerationManifest:
    """从所有已批准资产自动生成 Manifest（每资产一行）。

    每个 ManifestItem 通过 V3ManifestReference 关联到其来源 anchor/plan，
    替代旧的 reference_ids JSON 数组方案。
    """
    from app.models import (
        V3CharacterAnchorVersion as CA, V3PropAnchorVersion as PA, V3LocationViewVersion as LV,
    )

    style = (
        db.query(V3StyleBibleVersion)
        .filter(V3StyleBibleVersion.project_id == project_id, V3StyleBibleVersion.status == "approved")
        .order_by(V3StyleBibleVersion.id.desc())
        .first()
    )
    manifest = V3GenerationManifest(
        project_id=project_id,
        version=next_manifest_version(db, project_id),
        status="draft",
        style_bible_id=style.id if style else None,
        notes=notes,
    )
    db.add(manifest)
    db.flush()

    def add_item(
        key: str, asset_type: str, required_view: str,
        references: list[tuple[str, str, int | None]],
        prompt: str = "", negative: str = "", parent: str | None = None, scenes: list | None = None,
    ) -> None:
        item = V3ManifestItem(
            manifest_id=manifest.id, project_id=project_id,
            asset_stable_key=key, asset_type=asset_type, parent_key=parent,
            scenes=scenes or [], style_version_id=style.id if style else None,
            palette_version_id=style.palette_version_id if style else None,
            reference_ids=[], required_view=required_view,
            prompt=prompt, negative_constraints=negative,
        )
        db.add(item)
        db.flush()
        for ref_type, ref_key, ref_ver in references:
            db.add(V3ManifestReference(
                manifest_item_id=item.id,
                reference_type=ref_type,
                reference_key=ref_key,
                reference_version_id=ref_ver,
                role="primary",
            ))

    for a in db.query(CA).filter(CA.project_id == project_id, CA.status == "approved").all():
        views = ["front", "side", "back"]
        for view in views:
            add_item(
                key=a.stable_key, asset_type="character_anchor", required_view=view,
                references=[("character_anchor", a.stable_key, a.id)],
                prompt=f"角色 {a.name}（{a.stable_key}）{view} 视图。{_identity_text(a.identity_anchor)}。禁止漂移：{'；'.join(a.drift_prohibition)}",
                negative="面部变形，身份漂移，服装穿越",
            )
    for a in db.query(PA).filter(PA.project_id == project_id, PA.status == "approved").all():
        add_item(
            key=a.stable_key, asset_type="prop_anchor", required_view="hero",
            references=[("prop_anchor", a.stable_key, a.id)],
            prompt=f"道具 {a.name}（{a.stable_key}）。尺寸：{a.size}。材质：{a.material}。磨损：{a.wear_condition}。",
            negative="道具变形，材质错误",
        )
    for v in db.query(LV).filter(LV.project_id == project_id, LV.status == "approved").all():
        add_item(
            key=v.stable_key, asset_type="location_view", required_view="view",
            references=[("location_view", v.stable_key, v.id), ("spatial_plan", f"SPL-{v.spatial_plan_id}", v.spatial_plan_id)],
            prompt=f"地点关键视图 {v.name}。{v.description}。视角：{v.view_angle}。",
            negative="地理结构错误，透视错误",
        )
    db.commit()
    db.refresh(manifest)
    return manifest


def approve_manifest(db: Session, project_id: int, manifest_id: int, user_id: int) -> V3GenerationManifest:
    m = db.get(V3GenerationManifest, manifest_id)
    if not m or m.project_id != project_id:
        raise ValueError("生成清单不存在")
    if m.status != "draft":
        raise ValueError(f"当前状态 {m.status} 不可批准")
    m.status = "approved"
    m.approved_by = user_id
    from datetime import datetime, timezone
    m.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(m)
    return m


def get_manifest(db: Session, project_id: int, manifest_id: int) -> V3GenerationManifest | None:
    return db.query(V3GenerationManifest).filter(
        V3GenerationManifest.id == manifest_id,
        V3GenerationManifest.project_id == project_id,
    ).first()


def list_manifests(db: Session, project_id: int) -> list[V3GenerationManifest]:
    return (
        db.query(V3GenerationManifest)
        .filter(V3GenerationManifest.project_id == project_id)
        .order_by(V3GenerationManifest.id.desc())
        .all()
    )


def reference_out(r: V3ManifestReference) -> dict:
    return {
        "id": r.id,
        "reference_type": r.reference_type,
        "reference_key": r.reference_key,
        "reference_version_id": r.reference_version_id,
        "role": r.role,
    }


def item_out(i: V3ManifestItem) -> dict:
    return {
        "id": i.id, "asset_stable_key": i.asset_stable_key, "asset_type": i.asset_type,
        "parent_key": i.parent_key, "scenes": i.scenes,
        "style_version_id": i.style_version_id, "palette_version_id": i.palette_version_id,
        "reference_ids": i.reference_ids, "required_view": i.required_view,
        "prompt": i.prompt, "negative_constraints": i.negative_constraints,
        "aspect_ratio": i.aspect_ratio, "status": i.status, "notes": i.notes,
        "references": [reference_out(r) for r in i.references],
    }


def manifest_out(m: V3GenerationManifest, items: list[V3ManifestItem] | None = None) -> dict:
    out = {
        "id": m.id, "project_id": m.project_id, "version": m.version,
        "parent_version_id": m.parent_version_id, "status": m.status,
        "style_bible_id": m.style_bible_id, "notes": m.notes,
        "approved_by": m.approved_by, "approved_at": m.approved_at,
    }
    if items is not None:
        out["items"] = [item_out(i) for i in items]
    return out