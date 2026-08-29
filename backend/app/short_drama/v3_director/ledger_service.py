"""故事级台账服务：生成候选、校验、Checkpoion A 决策与门禁。

契约见 docs/v3-director-rfc.md §5.1：
- 台账绑定 SourceDocument / NovelAnalysisVersion
- StoryBeat：intensity 0-10，valence -5~+5，evidence_type ∈ {explicit,inferred,assumed}
- assumed 必须带 confidence；source_locator 必填
- 情感曲线直接查询 StoryBeat
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.v3_director import V3LedgerDecision, V3ScriptLedgerVersion, V3StoryBeat

VALID_EVIDENCE = {"explicit", "inferred", "assumed"}


def _beat_errors(beat: dict) -> list[dict]:
    """校验单个节拍数据。"""
    errors: list[dict] = []
    ref = str(beat.get("stable_key") or "?")
    if not beat.get("event"):
        errors.append({"field": "event", "message": "缺少事件", "ref": ref})
    intensity = beat.get("emotion_intensity")
    if not isinstance(intensity, (int, float)) or not (0 <= intensity <= 10):
        errors.append({"field": "emotion_intensity", "message": f"强度必须在 0-10，当前 {intensity}", "ref": ref})
    valence = beat.get("emotion_valence")
    if not isinstance(valence, (int, float)) or not (-5 <= valence <= 5):
        errors.append({"field": "emotion_valence", "message": f"效价必须在 -5~+5，当前 {valence}", "ref": ref})
    evidence = str(beat.get("evidence_type") or "inferred")
    if evidence not in VALID_EVIDENCE:
        errors.append({"field": "evidence_type", "message": f"证据等级无效：{evidence}", "ref": ref})
    if evidence == "assumed":
        conf = beat.get("confidence")
        if not isinstance(conf, (int, float)) or not (0 <= conf <= 1):
            errors.append({"field": "confidence", "message": "assumed 类必须提供 0-1 置信度", "ref": ref})
    if not str(beat.get("source_locator") or "").strip():
        errors.append({"field": "source_locator", "message": "缺少来源定位", "ref": ref})
    return errors


def validate_beats(beats: list[dict]) -> list[dict]:
    """校验节拍列表：单项校验 + 键唯一 + 依赖存在性。"""
    errors: list[dict] = []
    keys: set[str] = set()
    for index, beat in enumerate(beats):
        for e in _beat_errors(beat):
            errors.append({**e, "index": index})
        key = str(beat.get("stable_key") or "")
        if not key:
            errors.append({"field": "stable_key", "message": "缺少稳定键", "index": index})
        elif key in keys:
            errors.append({"field": "stable_key", "message": f"稳定键重复：{key}", "index": index})
        else:
            keys.add(key)
        dep = beat.get("causal_dependency")
        if dep and str(dep) not in keys and str(dep) != key:
            # 前向引用在第二轮校验中检查（收集后再看）
            pass
    # 因果依赖必须是更早出现的键
    seen: set[str] = set()
    for index, beat in enumerate(beats):
        dep = beat.get("causal_dependency")
        if dep:
            if str(dep) == beat.get("stable_key"):
                errors.append({"field": "causal_dependency", "message": "不能依赖自身", "index": index})
            elif str(dep) not in seen:
                errors.append({
                    "field": "causal_dependency",
                    "message": f"依赖的节拍 {dep} 不在此前或不存在",
                    "index": index,
                })
        seen.add(str(beat.get("stable_key") or ""))
    return errors


def next_version(db: Session, project_id: int) -> int:
    last = (
        db.query(V3ScriptLedgerVersion.version)
        .filter(V3ScriptLedgerVersion.project_id == project_id)
        .order_by(V3ScriptLedgerVersion.version.desc())
        .first()
    )
    return (last[0] if last else 0) + 1


def create_ledger_from_beats(
    db: Session,
    project_id: int,
    document_id: int | None,
    analysis_id: int | None,
    name: str,
    summary: str,
    content: dict,
    beats: list[dict],
    generation_record_id: int | None = None,
    provenance: dict | None = None,
) -> tuple[V3ScriptLedgerVersion, list[dict]]:
    """用节拍列表创建台账候选。返回 (ledger, validation_errors)。"""
    errors = validate_beats(beats)
    ledger = V3ScriptLedgerVersion(
        project_id=project_id,
        document_id=document_id,
        analysis_id=analysis_id,
        version=next_version(db, project_id),
        status="invalid" if errors else "candidate",
        name=name,
        summary=summary,
        content=content or {},
        validation_errors=errors,
        generation_record_id=generation_record_id,
        provenance=provenance or {},
    )
    db.add(ledger)
    db.flush()
    for index, beat in enumerate(sorted(beats, key=lambda b: b.get("order") or index)):
        db.add(V3StoryBeat(
            ledger_id=ledger.id,
            stable_key=str(beat.get("stable_key")),
            order=int(beat.get("order") or index),
            event=str(beat.get("event") or ""),
            goal=str(beat.get("goal") or ""),
            conflict=str(beat.get("conflict") or ""),
            reversal=str(beat.get("reversal") or ""),
            outcome=str(beat.get("outcome") or ""),
            causal_dependency=beat.get("causal_dependency"),
            characters=beat.get("characters") or [],
            emotion_intensity=float(beat.get("emotion_intensity") or 0),
            emotion_valence=float(beat.get("emotion_valence") or 0),
            dominant_emotion=str(beat.get("dominant_emotion") or ""),
            narrative_function=str(beat.get("narrative_function") or ""),
            evidence_type=str(beat.get("evidence_type") or "inferred"),
            confidence=beat.get("confidence"),
            source_locator=str(beat.get("source_locator") or ""),
        ))
    db.commit()
    db.refresh(ledger)
    return ledger, errors


def get_ledger(db: Session, project_id: int, ledger_id: int) -> V3ScriptLedgerVersion | None:
    return db.query(V3ScriptLedgerVersion).filter(
        V3ScriptLedgerVersion.id == ledger_id,
        V3ScriptLedgerVersion.project_id == project_id,
    ).first()


def latest_approved(db: Session, project_id: int) -> V3ScriptLedgerVersion | None:
    """获取最新已批准台账（场景级/下游资产的事实源）。"""
    return (
        db.query(V3ScriptLedgerVersion)
        .filter(
            V3ScriptLedgerVersion.project_id == project_id,
            V3ScriptLedgerVersion.status == "approved",
        )
        .order_by(V3ScriptLedgerVersion.id.desc())
        .first()
    )


def approve(db: Session, ledger: V3ScriptLedgerVersion, user_id: int) -> V3ScriptLedgerVersion:
    """批准候选台账；校验和未决项保留为建议，不阻断批准。"""
    if ledger.status not in ("candidate",):
        raise ValueError(f"当前状态 {ledger.status} 不可批准")
    ledger.status = "approved"
    ledger.approved_by = user_id
    from datetime import datetime, timezone
    ledger.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(ledger)
    return ledger


def emotion_curve(db: Session, ledger_id: int) -> list[dict]:
    """情感曲线数据——直接查询 StoryBeat，含假设标注和置信度。"""
    beats = (
        db.query(V3StoryBeat)
        .filter(V3StoryBeat.ledger_id == ledger_id)
        .order_by(V3StoryBeat.order)
        .all()
    )
    return [
        {
            "stable_key": b.stable_key,
            "order": b.order,
            "label": (b.event[:40] + "…") if len(b.event) > 40 else b.event,
            "intensity": round(b.emotion_intensity, 1),
            "valence": round(b.emotion_valence, 1),
            "dominant_emotion": b.dominant_emotion,
            "narrative_function": b.narrative_function,
            "evidence_type": b.evidence_type,
            "confidence": b.confidence,
            "source_locator": b.source_locator,
            "is_assumption": b.evidence_type == "assumed",
        }
        for b in beats
    ]


def curve_summary(curve: list[dict]) -> dict:
    """情感曲线摘要：最高峰、最低谷、转折点数量、节奏风险。"""
    if not curve:
        return {"peak": None, "trough": None, "turning_points": [], "rhythm_risk": ""}
    peak = max(curve, key=lambda p: p["intensity"])
    trough = min(curve, key=lambda p: p["intensity"])
    turning_points: list[dict] = []
    for i in range(1, len(curve) - 1):
        prev_v, cur_v, next_v = curve[i - 1]["valence"], curve[i]["valence"], curve[i + 1]["valence"]
        if (cur_v > prev_v and cur_v > next_v) or (cur_v < prev_v and cur_v < next_v):
            turning_points.append(curve[i])
    risk = ""
    assumptions = sum(1 for p in curve if p.get("is_assumption"))
    if assumptions:
        risk += f"{assumptions} 个假设节拍需要验证。"
    flat_run = max_run = 0
    for i in range(1, len(curve)):
        if abs(curve[i]["intensity"] - curve[i - 1]["intensity"]) < 1:
            flat_run += 1
            max_run = max(max_run, flat_run)
        else:
            flat_run = 0
    if max_run >= 3:
        risk += f"最长连续平坦段 {max_run} 个节拍，节奏可能拖沓。"
    return {"peak": peak, "trough": trough, "turning_points": turning_points, "rhythm_risk": risk.strip()}


# ---- Checkpoint A 决策 ----

def add_decision(
    db: Session, project_id: int, ledger_version_id: int, owner_id: int | None,
    question: str, options: list[str],
) -> V3LedgerDecision:
    d = V3LedgerDecision(
        project_id=project_id,
        ledger_version_id=ledger_version_id,
        owner_id=owner_id,
        question=question,
        options=[{"key": i + 1, "text": o} for i, o in enumerate(options)] or [],
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def resolve_decision(db: Session, decision_id: int, chosen: str, note: str = "", waive: bool = False) -> V3LedgerDecision:
    from datetime import datetime, timezone
    d = db.get(V3LedgerDecision, decision_id)
    if not d:
        raise ValueError("决策记录不存在")
    if d.status != "open":
        raise ValueError("决策已处理")
    d.chosen = chosen
    d.note = note
    d.status = "waived" if waive else "resolved"
    d.decided_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(d)
    return d


def list_decisions(db: Session, ledger_version_id: int) -> list[V3LedgerDecision]:
    return (
        db.query(V3LedgerDecision)
        .filter(V3LedgerDecision.ledger_version_id == ledger_version_id)
        .order_by(V3LedgerDecision.id)
        .all()
    )


def decisions_to_payload(decisions: list[V3LedgerDecision]) -> list[dict]:
    return [
        {
            "id": d.id,
            "question": d.question,
            "options": d.options,
            "chosen": d.chosen,
            "status": d.status,
            "note": d.note,
            "decided_at": d.decided_at.isoformat() if d.decided_at else None,
        }
        for d in decisions
    ]
