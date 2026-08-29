"""风格圣经服务：候选管理（最多三个）、推荐、版本审批、Checkpoint B 门禁。

契约见 docs/v3-director-rfc.md 和实施计划第 4 轮：
- 最多三个候选、推荐项、版本审批、参考素材 provenance
- 修改已批准风格产生新候选，旧版本保持不变
- 无批准风格时禁止批量创建实际锚点生成任务（Checkpoint B）
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.v3_director import V3PaletteVersion, V3StyleBibleVersion

MAX_CANDIDATES = 3


def next_version(db: Session, project_id: int) -> int:
    last = (
        db.query(V3StyleBibleVersion.version)
        .filter(V3StyleBibleVersion.project_id == project_id)
        .order_by(V3StyleBibleVersion.version.desc())
        .first()
    )
    return (last[0] if last else 0) + 1


def _candidate_count(db: Session, project_id: int) -> int:
    return (
        db.query(V3StyleBibleVersion)
        .filter(V3StyleBibleVersion.project_id == project_id, V3StyleBibleVersion.status == "candidate")
        .count()
    )


def create_candidate(
    db: Session,
    project_id: int,
    fields: dict,
    palette: dict | None = None,
    generation_record_id: int | None = None,
    provenance: dict | None = None,
) -> V3StyleBibleVersion:
    """创建风格圣经候选（含可选色卡）。候选满 3 个时拒绝。"""
    if _candidate_count(db, project_id) >= MAX_CANDIDATES:
        raise ValueError(f"最多保留 {MAX_CANDIDATES} 个候选，请先处理现有候选")
    version = next_version(db, project_id)
    bible = V3StyleBibleVersion(
        project_id=project_id,
        version=version,
        status="candidate",
        name=str(fields.get("name") or f"风格圣经 v{version}"),
        visual_thesis=str(fields.get("visual_thesis") or ""),
        era=str(fields.get("era") or ""),
        realism=str(fields.get("realism") or ""),
        composition=str(fields.get("composition") or ""),
        aspect_ratio=str(fields.get("aspect_ratio") or "9:16"),
        lens_language=str(fields.get("lens_language") or ""),
        lighting=str(fields.get("lighting") or ""),
        texture_material=str(fields.get("texture_material") or ""),
        sound_world=str(fields.get("sound_world") or ""),
        non_negotiables=fields.get("non_negotiables") or [],
        reference_ids=fields.get("reference_ids") or [],
        generation_record_id=generation_record_id,
        provenance=provenance or {"ai_generated": True},
    )
    db.add(bible)
    db.flush()
    if palette and isinstance(palette, dict):
        _create_palette(db, project_id, bible.id, palette)
    db.commit()
    db.refresh(bible)
    return bible


def _create_palette(db: Session, project_id: int, style_bible_id: int, p: dict) -> V3PaletteVersion:
    version = (
        db.query(V3PaletteVersion.version)
        .filter(V3PaletteVersion.project_id == project_id)
        .order_by(V3PaletteVersion.version.desc())
        .first()
    )
    row = V3PaletteVersion(
        project_id=project_id,
        style_bible_id=style_bible_id,
        version=(version[0] if version else 0) + 1,
        name=str(p.get("name") or ""),
        scope=str(p.get("scope") or "general"),
        time_variant=str(p.get("time_variant") or ""),
        primary_color=str(p.get("primary_color") or ""),
        secondary_color=str(p.get("secondary_color") or ""),
        accent_color=str(p.get("accent_color") or ""),
        neutral_color=str(p.get("neutral_color") or ""),
        skin_tone_protection=str(p.get("skin_tone_protection") or ""),
        forbidden_colors=p.get("forbidden_colors") or [],
        exposure_notes=str(p.get("exposure_notes") or ""),
        provenance=p.get("provenance") or {},
    )
    db.add(row)
    db.flush()
    return row


def get(db: Session, project_id: int, style_id: int) -> V3StyleBibleVersion | None:
    return db.query(V3StyleBibleVersion).filter(
        V3StyleBibleVersion.id == style_id,
        V3StyleBibleVersion.project_id == project_id,
    ).first()


def latest_approved(db: Session, project_id: int) -> V3StyleBibleVersion | None:
    """获取最新已批准风格圣经（Checkpoint B 的事实源）。"""
    return (
        db.query(V3StyleBibleVersion)
        .filter(V3StyleBibleVersion.project_id == project_id, V3StyleBibleVersion.status == "approved")
        .order_by(V3StyleBibleVersion.id.desc())
        .first()
    )


def check_b(db: Session, project_id: int) -> dict:
    """Checkpoint B 状态检查：是否存在已批准风格圣经和关联色卡。"""
    approved = latest_approved(db, project_id)
    if not approved:
        return {"passed": False, "reason": "没有已批准的风格圣经"}
    palette = (
        db.query(V3PaletteVersion)
        .filter(V3PaletteVersion.style_bible_id == approved.id)
        .order_by(V3PaletteVersion.id.desc())
        .first()
    )
    if not palette:
        return {"passed": False, "reason": "批准的风格圣经没有关联色卡"}
    return {"passed": True, "style_id": approved.id, "style_version": approved.version, "palette_id": palette.id}


def derive_candidate(
    db: Session, parent_id: int, fields: dict, palette: dict | None = None,
    generation_record_id: int | None = None,
) -> V3StyleBibleVersion:
    """从已批准版本派生新候选（修改的唯一方式）。"""
    parent = db.get(V3StyleBibleVersion, parent_id)
    if not parent:
        raise ValueError("父风格圣经不存在")
    if parent.status != "approved":
        raise ValueError("只能从已批准的版本派生新候选")
    merged = {
        "name": fields.get("name") or parent.name,
        "visual_thesis": fields.get("visual_thesis", parent.visual_thesis),
        "era": fields.get("era", parent.era),
        "realism": fields.get("realism", parent.realism),
        "composition": fields.get("composition", parent.composition),
        "aspect_ratio": fields.get("aspect_ratio", parent.aspect_ratio),
        "lens_language": fields.get("lens_language", parent.lens_language),
        "lighting": fields.get("lighting", parent.lighting),
        "texture_material": fields.get("texture_material", parent.texture_material),
        "sound_world": fields.get("sound_world", parent.sound_world),
        "non_negotiables": fields.get("non_negotiables", parent.non_negotiables),
        "reference_ids": fields.get("reference_ids", parent.reference_ids),
    }
    return create_candidate(
        db, parent.project_id, merged, palette,
        generation_record_id=generation_record_id,
        provenance={"derived_from": parent.id},
    )


def list_bibles(db: Session, project_id: int) -> list[V3StyleBibleVersion]:
    return (
        db.query(V3StyleBibleVersion)
        .filter(V3StyleBibleVersion.project_id == project_id)
        .order_by(V3StyleBibleVersion.id.desc())
        .all()
    )


def bible_out(bible: V3StyleBibleVersion, palettes: list[V3PaletteVersion] | None = None) -> dict:
    out = {
        "id": bible.id,
        "project_id": bible.project_id,
        "version": bible.version,
        "parent_version_id": bible.parent_version_id,
        "status": bible.status,
        "name": bible.name,
        "visual_thesis": bible.visual_thesis,
        "era": bible.era,
        "realism": bible.realism,
        "composition": bible.composition,
        "aspect_ratio": bible.aspect_ratio,
        "lens_language": bible.lens_language,
        "lighting": bible.lighting,
        "texture_material": bible.texture_material,
        "sound_world": bible.sound_world,
        "non_negotiables": bible.non_negotiables,
        "reference_ids": bible.reference_ids,
        "validation_errors": bible.validation_errors,
        "approved_by": bible.approved_by,
        "approved_at": bible.approved_at,
        "palette_version_id": bible.palette_version_id,
        "created_at": bible.created_at,
    }
    if palettes is not None:
        out["palettes"] = [
            {
                "id": p.id, "version": p.version, "name": p.name, "scope": p.scope,
                "time_variant": p.time_variant, "primary_color": p.primary_color,
                "secondary_color": p.secondary_color, "accent_color": p.accent_color,
                "neutral_color": p.neutral_color, "skin_tone_protection": p.skin_tone_protection,
                "forbidden_colors": p.forbidden_colors, "exposure_notes": p.exposure_notes,
            }
            for p in palettes
        ]
    return out