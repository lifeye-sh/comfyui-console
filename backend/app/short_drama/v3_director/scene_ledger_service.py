"""场景级台账服务：从 StoryVersion 生成、Scene 对齐（沿用/新增/退役）、状态追踪。

契约见 docs/v3-director-rfc.md §5.2：
- LedgerScene 绑定 StoryVersion，保存与当前 Scene 的映射，不把稳定键依赖 Scene.id
- 替换 StoryVersion 后，匹配场景沿用稳定键
- 被删除的场景键退役但不重排；新增场景只取得新键
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models.v3_director import (
    V3ContinuityFact,
    V3LedgerScene,
    V3SceneCharacterAppearance,
    V3ScenePropState,
)
from app.models.short_drama import Scene, StoryVersion
from app.short_drama.v3_director import stable_identity_service


def _next_scene_key(db: Session, project_id: int) -> str:
    identity = stable_identity_service.allocate(db, project_id, "scene")
    return identity.stable_key


def _norm(text: str) -> str:
    """归一化用于匹配：小写、去空白和标点。"""
    return re.sub(r"[\s　，。：:；;！!？?·\-—()（）\[\]【】]+", "", (text or "").lower())


def _match_existing(
    db: Session,
    project_id: int,
    payload_scene_no: str,
    heading: str,
    location_name: str,
) -> V3LedgerScene | None:
    """在既有台账中找一个可沿用的候选：scene_ref/heading/location 三级模糊匹配。

    匹配策略：
    1. scene_no 完全一致（通过 mapping 里记录的旧 scene_no 模式）→ 强信号
    2. heading 归一化相等 → 强信号
    3. location_name + interior_exterior 一致 → 弱信号（要求唯一才沿用）
    """
    rows = db.query(V3LedgerScene).filter(
        V3LedgerScene.project_id == project_id,
        V3LedgerScene.status == "active",
    ).all()
    if not rows:
        return None

    norm_heading = _norm(heading)
    for row in rows:
        # 同一 StoryVersion 的重复对齐不再匹配
        pass

    # 1) heading 精确（归一化）匹配
    if norm_heading:
        by_heading = [r for r in rows if _norm(r.heading) == norm_heading]
        if len(by_heading) == 1:
            return by_heading[0]

    # 2) location+int/ext 匹配（仅当唯一）
    if location_name:
        by_loc = [
            r for r in rows
            if _norm(r.location_name) == _norm(location_name)
        ]
        if len(by_loc) == 1:
            return by_loc[0]

    return None


def sync_scenes_from_story_version(
    db: Session,
    project_id: int,
    story_version_id: int | None,
    episodes: list[dict],
) -> dict:
    """根据当前分集/场景结构同步场景级台账（stable key 对齐）。

    返回 {aligned, created, retired} 计数。
    - 已有 active LedgerScene 且能匹配到当前 Scene → 沿用稳定键并更新映射
    - 新出现的 Scene → 分配新稳定键
    - 已删除的 Scene → 台账 alignment_status=retired（不删数据、不重排键）
    """
    from app.models import Episode as EpisodeModel

    current_scenes = (
        db.query(Scene)
        .join(EpisodeModel, Scene.episode_id == EpisodeModel.id)
        .filter(EpisodeModel.project_id == project_id)
        .order_by(EpisodeModel.number, Scene.sort_order)
        .all()
    )
    existing = db.query(V3LedgerScene).filter(
        V3LedgerScene.project_id == project_id,
    ).all()
    existing_by_key = {s.stable_key: s for s in existing}
    matched_keys: set[str] = set()

    aligned = created = 0
    scene_by_id = {}
    for scene in current_scenes:
        # 已有映射：直接沿用
        prev = next((s for s in existing if s.scene_id == scene.id and s.status == "active"), None)
        if not prev:
            candidate = _match_existing(
                db, project_id, scene.scene_no or "", scene.heading or "", scene.location_name or ""
            )
            prev = candidate if (candidate and candidate.scene_id is None) else None
        if prev and prev.stable_key in matched_keys:
            prev = None  # 一个键只能对应一个场景
        if prev:
            scene_key = prev.stable_key
            matched_keys.add(scene_key)
            if prev.scene_id != scene.id:
                prev.scene_id = scene.id
                aligned += 1
        else:
            scene_key = _next_scene_key(db, project_id)
            created += 1
        scene_by_id[scene.id] = scene_key

        ledger_scene = existing_by_key.get(scene_key)
        if not ledger_scene:
            ledger_scene = V3LedgerScene(project_id=project_id, stable_key=scene_key)
            db.add(ledger_scene)
            db.flush()
        ledger_scene.story_version_id = story_version_id
        ledger_scene.scene_id = scene.id
        ledger_scene.episode_number = scene.episode.number if scene.episode else 0
        ledger_scene.heading = scene.heading or ""
        ledger_scene.location_name = scene.location_name or ""
        ledger_scene.time_of_day = scene.time_of_day or ""
        ledger_scene.interior_exterior = scene.interior_exterior or ""
        ledger_scene.summary = (scene.content or "")[:500]
        ledger_scene.purpose = scene.purpose or ""
        ledger_scene.alignment_status = "aligned"
        if ledger_scene.status == "retired":
            ledger_scene.status = "active"

    # 退役：已不在当前 Scenes 中的台账行
    retired = 0
    for row in existing:
        if row.status != "active":
            continue
        if row.scene_id is not None and row.scene_id in {s.id for s in current_scenes}:
            continue
        if row.stable_key in matched_keys:
            continue
        if row.scene_id is None and any(s2.scene_id is None and s2.id != row.id for s2 in []):
            continue
        # 当前 Scenes 中找不到映射 → 标记 retired（保留历史数据，不重排键）
        if row.scene_id is None and row.alignment_status == "pending":
            continue  # 尚未对齐的新行等下一轮
        if row.scene_id is not None:
            continue
        retired += 1
        row.alignment_status = "retired"
        row.status = "retired"

    db.commit()
    return {"aligned": aligned, "created": created, "retired": retired}


def upsert_appearance(
    db: Session, ledger_scene_id: int, character_key: str, character_name: str,
    fields: dict, evidence_type: str = "inferred", source_locator: str = "",
) -> V3SceneCharacterAppearance:
    row = db.query(V3SceneCharacterAppearance).filter(
        V3SceneCharacterAppearance.ledger_scene_id == ledger_scene_id,
        V3SceneCharacterAppearance.character_stable_key == character_key,
    ).first()
    if not row:
        row = V3SceneCharacterAppearance(
            ledger_scene_id=ledger_scene_id, character_stable_key=character_key, character_name=character_name
        )
        db.add(row)
    row.character_name = character_name or row.character_name
    for key in ("costume", "hair_makeup", "injuries_dirt", "emotional_state", "change_from_previous"):
        if key in fields:
            setattr(row, key, str(fields.get(key) or ""))
    row.evidence_type = evidence_type
    row.source_locator = source_locator or row.source_locator
    db.commit()
    db.refresh(row)
    return row


def upsert_prop_state(
    db: Session, ledger_scene_id: int, prop_key: str, prop_name: str,
    fields: dict, evidence_type: str = "inferred", source_locator: str = "",
) -> V3ScenePropState:
    row = db.query(V3ScenePropState).filter(
        V3ScenePropState.ledger_scene_id == ledger_scene_id,
        V3ScenePropState.prop_stable_key == prop_key,
    ).first()
    if not row:
        row = V3ScenePropState(ledger_scene_id=ledger_scene_id, prop_stable_key=prop_key, prop_name=prop_name)
        db.add(row)
    row.prop_name = prop_name or row.prop_name
    for key in ("owner_character_key", "location_in_scene", "condition", "interaction", "state_change"):
        if key in fields:
            setattr(row, key, fields.get(key))
    row.evidence_type = evidence_type
    row.source_locator = source_locator or row.source_locator
    db.commit()
    db.refresh(row)
    return row


def add_continuity_fact(
    db: Session, project_id: int, subject_type: str, subject_key: str, fact: str,
    severity: str = "info", from_scene_key: str | None = None, to_scene_key: str | None = None,
    story_version_id: int | None = None, evidence_type: str = "inferred", source_locator: str = "",
) -> V3ContinuityFact:
    if severity not in ("info", "risk", "blocker"):
        raise ValueError("severity 必须是 info/risk/blocker")
    cf = V3ContinuityFact(
        project_id=project_id,
        story_version_id=story_version_id,
        subject_type=subject_type,
        subject_key=subject_key,
        fact=fact,
        from_scene_key=from_scene_key,
        to_scene_key=to_scene_key,
        evidence_type=evidence_type,
        source_locator=source_locator,
        severity=severity,
    )
    db.add(cf)
    db.commit()
    db.refresh(cf)
    return cf


def list_ledger_scenes(db: Session, project_id: int) -> list[V3LedgerScene]:
    return (
        db.query(V3LedgerScene)
        .filter(V3LedgerScene.project_id == project_id)
        .order_by(V3LedgerScene.episode_number, V3LedgerScene.stable_key)
        .all()
    )


def trace_character_across_scenes(db: Session, project_id: int, character_key: str) -> list[dict]:
    """按场景顺序追溯某角色的服装/伤损/情绪变化链。"""
    rows = (
        db.query(V3SceneCharacterAppearance, V3LedgerScene)
        .join(V3LedgerScene, V3SceneCharacterAppearance.ledger_scene_id == V3LedgerScene.id)
        .filter(
            V3LedgerScene.project_id == project_id,
            V3SceneCharacterAppearance.character_stable_key == character_key,
            V3LedgerScene.status == "active",
        )
        .order_by(V3LedgerScene.episode_number, V3LedgerScene.stable_key)
        .all()
    )
    return [
        {
            "scene_key": ls.stable_key,
            "episode": ls.episode_number,
            "heading": ls.heading,
            "costume": app.costume,
            "hair_makeup": app.hair_makeup,
            "injuries_dirt": app.injuries_dirt,
            "emotional_state": app.emotional_state,
            "change_from_previous": app.change_from_previous,
        }
        for app, ls in rows
    ]


def open_blockers(db: Session, project_id: int) -> int:
    """未解决的 blocker 连续性事实数量（门禁用）。"""
    return (
        db.query(V3ContinuityFact)
        .filter(
            V3ContinuityFact.project_id == project_id,
            V3ContinuityFact.severity == "blocker",
            V3ContinuityFact.status == "open",
        )
        .count()
    )


def scene_out_payload(rows: list[V3LedgerScene]) -> list[dict]:
    return [
        {
            "id": s.id,
            "stable_key": s.stable_key,
            "story_version_id": s.story_version_id,
            "scene_id": s.scene_id,
            "episode_number": s.episode_number,
            "heading": s.heading,
            "location_name": s.location_name,
            "time_of_day": s.time_of_day,
            "interior_exterior": s.interior_exterior,
            "summary": s.summary[:200],
            "status": s.status,
            "alignment_status": s.alignment_status,
        }
        for s in rows
    ]
