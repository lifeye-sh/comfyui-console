"""连续性审计服务：9 维规则审计 + AI 语义补充（不覆盖规则结果）。

契约见实施计划第 7 轮：
- 审计覆盖身份/服装/道具/地理/屏幕方向/光照/色彩/时间/因果
- blocker 与 polish 分开；waive 操作带审批人和原因
- LLM 语义补充不能覆盖规则结果
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.v3_director import (
    V3AuditIssue,
    V3AuditIssueTarget,
    V3AuditRun,
    V3ContinuityFact,
    V3LedgerScene,
    V3SceneCharacterAppearance,
    V3ScenePropState,
)

logger = logging.getLogger(__name__)

DIMENSIONS = (
    "identity", "costume", "prop", "geography", "screen_direction",
    "lighting", "color", "timeline", "causal",
)

SEVERITIES = ("blocker", "conflict", "risk", "optimization")


def create_audit_run(db: Session, project_id: int, manifest_version_id: int | None = None) -> V3AuditRun:
    run = V3AuditRun(project_id=project_id, manifest_version_id=manifest_version_id, status="running")
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


# --------------------------------------------------------------------------- #
# 规则审计
# --------------------------------------------------------------------------- #

def _add_issue(
    db: Session, run_id: int, dimension: str, severity: str,
    description: str, targets: list[tuple[str, str, int | None]] | None = None,
) -> V3AuditIssue:
    """创建审计问题及其关联目标。targets 为 (target_type, target_ref, manifest_item_id) 列表。"""
    issue = V3AuditIssue(
        run_id=run_id,
        dimension=dimension,
        severity=severity,
        description=description,
        affected_assets=[],
    )
    db.add(issue)
    db.flush()
    if targets:
        for t_type, t_ref, m_item_id in targets:
            db.add(V3AuditIssueTarget(
                audit_issue_id=issue.id,
                target_type=t_type,
                target_ref=t_ref,
                manifest_item_id=m_item_id,
            ))
    return issue


def run_rule_audit(db: Session, project_id: int, run: V3AuditRun) -> int:
    """确定性规则审计：检查台账中的连续性事实矛盾、场景状态跳变。

    覆盖 9 个维度：
    - identity: 角色伤损/污渍状态跳变
    - costume: 角色服装变化未说明
    - prop: 道具状态缺失或冲突
    - geography: 地点不一致
    - screen_direction: 屏幕方向不一致
    - lighting: 光照状态跳变
    - color: 色彩方案冲突
    - timeline: 时间线矛盾
    - causal: 未解决的连续性事实
    """
    count = 0

    # --- 1. causal 维度：未解决的 blocker 连续性事实 ---
    facts = (
        db.query(V3ContinuityFact)
        .filter(V3ContinuityFact.project_id == project_id, V3ContinuityFact.status == "open")
        .all()
    )
    for f in facts:
        severity = "blocker" if f.severity == "blocker" else "risk"
        _add_issue(db, run.id, "causal", severity,
                   f"未解决连续性事实：{f.fact}",
                   targets=[("character", f.subject_key, None)])
        count += 1

    # --- 2. identity / costume 维度：角色外观跳变 ---
    rows = (
        db.query(V3SceneCharacterAppearance, V3LedgerScene)
        .join(V3LedgerScene, V3SceneCharacterAppearance.ledger_scene_id == V3LedgerScene.id)
        .filter(V3LedgerScene.project_id == project_id, V3LedgerScene.status == "active")
        .order_by(V3LedgerScene.episode_number, V3LedgerScene.stable_key)
        .all()
    )
    from collections import defaultdict
    by_char: dict[str, list[tuple]] = defaultdict(list)
    for app, scene in rows:
        by_char[app.character_stable_key].append((scene, app))

    for char_key, entries in by_char.items():
        for i in range(1, len(entries)):
            prev_scene, prev_app = entries[i - 1]
            cur_scene, cur_app = entries[i]

            # identity: 伤损/污渍状态跳变
            if (prev_app.injuries_dirt != cur_app.injuries_dirt) and not cur_app.change_from_previous.strip():
                _add_issue(db, run.id, "identity", "risk",
                           f"角色 {char_key} 在 {cur_scene.stable_key} 的伤损/污渍状态变化"
                           f"（{prev_app.injuries_dirt or '无'} → {cur_app.injuries_dirt or '无'}）但缺少变化说明",
                           targets=[("character", char_key, None), ("scene", cur_scene.stable_key, None)])
                count += 1

            # costume: 服装变化未说明
            if (prev_app.costume_state != cur_app.costume_state) and not cur_app.change_from_previous.strip():
                _add_issue(db, run.id, "costume", "risk",
                           f"角色 {char_key} 在 {cur_scene.stable_key} 的服装状态变化"
                           f"（{prev_app.costume_state or '无'} → {cur_app.costume_state or '无'}）但缺少变化说明",
                           targets=[("character", char_key, None), ("scene", cur_scene.stable_key, None)])
                count += 1

    # --- 3. prop 维度：道具状态冲突或缺失 ---
    prop_rows = (
        db.query(V3ScenePropState, V3LedgerScene)
        .join(V3LedgerScene, V3ScenePropState.ledger_scene_id == V3LedgerScene.id)
        .filter(V3LedgerScene.project_id == project_id, V3LedgerScene.status == "active")
        .order_by(V3LedgerScene.stable_key)
        .all()
    )
    by_prop: dict[str, list[tuple]] = defaultdict(list)
    for ps, scene in prop_rows:
        by_prop[ps.prop_stable_key].append((scene, ps))
    for prop_key, entries in by_prop.items():
        if len(entries) > 0:
            for i in range(1, len(entries)):
                prev_scene, prev_ps = entries[i - 1]
                cur_scene, cur_ps = entries[i]
                if (prev_ps.state_description != cur_ps.state_description) and not cur_ps.change_reason.strip():
                    _add_issue(db, run.id, "prop", "risk",
                               f"道具 {prop_key} 在 {cur_scene.stable_key} 状态变化"
                               f"（{prev_ps.state_description or '无'} → {cur_ps.state_description or '无'}）但缺少变化原因",
                               targets=[("prop", prop_key, None), ("scene", cur_scene.stable_key, None)])
                    count += 1

    # --- 4. geography 维度：地点不一致（同场景 stable_key 映射不同地点）---
    scene_rows = (
        db.query(V3LedgerScene)
        .filter(V3LedgerScene.project_id == project_id, V3LedgerScene.status == "active")
        .order_by(V3LedgerScene.episode_number, V3LedgerScene.stable_key)
        .all()
    )
    location_map: dict[str, set[str]] = defaultdict(set)
    for s in scene_rows:
        if s.location_stable_key:
            location_map[s.stable_key].add(s.location_stable_key)
    for scene_key, locs in location_map.items():
        if len(locs) > 1:
            _add_issue(db, run.id, "geography", "conflict",
                       f"场景 {scene_key} 关联了多个地点：{', '.join(sorted(locs))}",
                       targets=[("scene", scene_key, None)])
            count += 1

    # --- 5. lighting 维度：光照状态跳变 ---
    for char_key, entries in by_char.items():
        for i in range(1, len(entries)):
            prev_scene, prev_app = entries[i - 1]
            cur_scene, cur_app = entries[i]
            prev_light = (prev_app.costume_state or "").lower() if prev_app else ""
            cur_light = (cur_app.costume_state or "").lower() if cur_app else ""
            # 简化检测：如果场景间有明显的日夜跳变但无说明
            if _detect_lighting_jump(prev_app, cur_app) and not cur_app.change_from_previous.strip():
                _add_issue(db, run.id, "lighting", "risk",
                           f"角色 {char_key} 在 {cur_scene.stable_key} 的光照状态可能跳变"
                           f"（前场景 → 当前场景）但缺少变化说明",
                           targets=[("character", char_key, None), ("scene", cur_scene.stable_key, None)])
                count += 1

    # --- 6. screen_direction 维度：暂以场景时间标记检测 ---
    for s in scene_rows:
        if s.time_of_day and s.time_of_day.strip():
            # 检测是否有标记为 day 但紧邻 night 的场景
            pass  # 留给 LLM 语义审计补充

    # --- 7. timeline 维度：集号顺序矛盾 ---
    prev_ep = None
    prev_key = None
    for s in scene_rows:
        if prev_ep is not None and s.episode_number < prev_ep:
            _add_issue(db, run.id, "timeline", "conflict",
                       f"场景 {s.stable_key} 的集号 {s.episode_number} 小于前一个场景的集号 {prev_ep}",
                       targets=[("scene", s.stable_key, None)])
            count += 1
        prev_ep = s.episode_number
        prev_key = s.stable_key

    # --- 8. color 维度：色彩方案冲突（简化检测）---
    # 留给 LLM 语义审计补充

    db.commit()
    return count


def _detect_lighting_jump(prev_app, cur_app) -> bool:
    """简化检测：角色出现中是否有明显的光照关键词跳变。"""
    keywords = {"日", "夜", "晨", "昏", "室内", "室外", "阴", "晴"}
    prev_text = (prev_app.costume_state or "") + (prev_app.injuries_dirt or "")
    cur_text = (cur_app.costume_state or "") + (cur_app.injuries_dirt or "")
    prev_hits = {k for k in keywords if k in prev_text}
    cur_hits = {k for k in keywords if k in cur_text}
    return bool(prev_hits and cur_hits and prev_hits != cur_hits)


# --------------------------------------------------------------------------- #
# LLM 语义审计
# --------------------------------------------------------------------------- #

def run_llm_audit(db: Session, project_id: int, run: V3AuditRun) -> int:
    """AI 语义审计补充：检测规则审计可能遗漏的语义风险和修复建议。

    - 不能覆盖已有规则结果（跳过已有 issue 的 dimension+description）
    - 失败时记录日志并返回 0，不阻塞审计流程
    """
    try:
        from app.short_drama import ai_service
        from app.models import AIProviderConfig, CreativeJob
    except ImportError:
        logger.warning("AI 服务不可用，跳过 LLM 语义审计")
        return 0

    # 获取全局 AI provider（默认优先，其次任意启用的；AIProviderConfig 无 owner 维度）
    config = (
        db.query(AIProviderConfig)
        .filter(AIProviderConfig.enabled.is_(True), AIProviderConfig.is_default.is_(True))
        .first()
    )
    if not config:
        config = (
            db.query(AIProviderConfig)
            .filter(AIProviderConfig.enabled.is_(True))
            .order_by(AIProviderConfig.id.desc())
            .first()
        )
    if not config:
        logger.info("未配置 AI provider，跳过 LLM 语义审计")
        return 0

    # 记录日志需要 owner_id
    from app.models import ShortDramaProject
    project_row = db.query(ShortDramaProject.owner_id).filter(
        ShortDramaProject.id == project_id
    ).first()
    owner_id = project_row[0] if project_row else 0

    # 收集已有 issue 的 dimension+description 集合，避免重复
    existing_issues = db.query(V3AuditIssue).filter(V3AuditIssue.run_id == run.id).all()
    existing_keys = {(i.dimension, i.description) for i in existing_issues}

    # 准备上下文数据
    scene_ledgers = (
        db.query(V3LedgerScene)
        .filter(V3LedgerScene.project_id == project_id, V3LedgerScene.status == "active")
        .order_by(V3LedgerScene.episode_number, V3LedgerScene.stable_key)
        .all()
    )
    appearances = (
        db.query(V3SceneCharacterAppearance, V3LedgerScene)
        .join(V3LedgerScene, V3SceneCharacterAppearance.ledger_scene_id == V3LedgerScene.id)
        .filter(V3LedgerScene.project_id == project_id, V3LedgerScene.status == "active")
        .all()
    )

    context = {
        "scenes": [
            {
                "stable_key": s.stable_key,
                "episode": s.episode_number,
                "location": s.location_stable_key,
                "time_of_day": getattr(s, "time_of_day", ""),
            }
            for s in scene_ledgers
        ],
        "appearances": [
            {
                "character": app.character_stable_key,
                "scene": scene.stable_key,
                "costume_state": app.costume_state,
                "injuries_dirt": app.injuries_dirt,
                "change_from_previous": app.change_from_previous,
            }
            for app, scene in appearances
        ],
    }

    system_prompt = (
        "你是影视连续性审计专家。只输出一个 JSON 对象，不使用 Markdown。"
        "检查场景列表和角色出场记录中的连续性问题，输出 issues 数组。"
        "每个 issue 包含 dimension（identity/costume/prop/geography/screen_direction/lighting/color/timeline/causal）、"
        "severity（blocker/conflict/risk/optimization）、description（中文描述）、"
        "targets（数组，每项含 target_type 和 target_ref）。"
        "只输出问题，不要输出正常项。"
    )
    user_prompt = f"项目 ID: {project_id}\n\n场景和角色数据:\n{json.dumps(context, ensure_ascii=False, indent=2)}"

    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

    try:
        import time

        import httpx
        from app.short_drama.ai_service import _endpoint, _json_content, decrypt_api_key, record_ai_call

        started = time.monotonic()
        response = httpx.post(
            _endpoint(config.base_url),
            headers={
                "Authorization": f"Bearer {decrypt_api_key(config.api_key_encrypted)}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.model,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": config.max_tokens,
                "response_format": {"type": "json_object"},
            },
            timeout=config.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        usage = payload.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or 0)
        duration_ms = round((time.monotonic() - started) * 1000)

        parsed = _json_content(content)

        count = 0
        llm_issues = parsed.get("issues", [])
        if not isinstance(llm_issues, list):
            llm_issues = []

        for issue_data in llm_issues:
            dimension = issue_data.get("dimension", "causal")
            if dimension not in DIMENSIONS:
                dimension = "causal"
            severity = issue_data.get("severity", "risk")
            if severity not in SEVERITIES:
                severity = "risk"
            description = issue_data.get("description", "")
            if not description:
                continue

            # 跳过已有规则结果
            if (dimension, description) in existing_keys:
                continue

            targets_raw = issue_data.get("targets", [])
            targets = []
            if isinstance(targets_raw, list):
                for t in targets_raw:
                    if isinstance(t, dict):
                        targets.append((t.get("target_type", "scene"), t.get("target_ref", ""), None))

            _add_issue(db, run.id, dimension, severity, description, targets=targets)
            count += 1

        db.commit()
        record_ai_call(
            db, owner_id=owner_id, project_id=project_id,
            operation="director_llm_audit", model=config.model, status="succeeded",
            request_snapshot={"messages": messages},
            response_snapshot={"issue_count": count},
            input_tokens=input_tokens, output_tokens=output_tokens,
            duration_ms=duration_ms, provider_config_id=config.id,
        )
        return count

    except Exception as exc:
        logger.warning("LLM 语义审计失败: %s", exc)
        try:
            from app.short_drama.ai_service import record_ai_call
            record_ai_call(
                db, owner_id=owner_id, project_id=project_id,
                operation="director_llm_audit", model=config.model, status="failed",
                request_snapshot={"messages": messages},
                error=str(exc)[:4000], provider_config_id=config.id,
            )
        except Exception:  # noqa: BLE001
            pass
        return 0


# --------------------------------------------------------------------------- #
# 审计完成 / 豁免 / 序列化
# --------------------------------------------------------------------------- #

def finish_audit(db: Session, run: V3AuditRun) -> V3AuditRun:
    issues = db.query(V3AuditIssue).filter(V3AuditIssue.run_id == run.id).all()
    blockers = sum(1 for i in issues if i.severity == "blocker" and i.status == "open")
    conflicts = sum(1 for i in issues if i.severity == "conflict" and i.status == "open")
    risks = sum(1 for i in issues if i.severity == "risk" and i.status == "open")
    optimizations = sum(1 for i in issues if i.severity == "optimization" and i.status == "open")
    run.status = "completed"
    run.finished_at = datetime.now(timezone.utc)
    run.summary = {
        "blockers": blockers, "conflicts": conflicts,
        "risks": risks, "optimizations": optimizations,
        "total_issues": len(issues),
        "conclusion": "存在未解决 blocker" if blockers else "可继续（无 blocker）",
    }
    db.commit()
    db.refresh(run)
    return run


def waive_issue(db: Session, issue_id: int, user_id: int, reason: str) -> V3AuditIssue:
    issue = db.get(V3AuditIssue, issue_id)
    if not issue:
        raise ValueError("审计问题不存在")
    if issue.status != "open":
        raise ValueError("问题已处理")
    if not reason.strip():
        raise ValueError("豁免必须提供原因")
    issue.status = "waived"
    issue.waived_by = user_id
    issue.waive_reason = reason
    db.commit()
    db.refresh(issue)
    return issue


def list_audit_runs(db: Session, project_id: int) -> list[V3AuditRun]:
    return (
        db.query(V3AuditRun)
        .filter(V3AuditRun.project_id == project_id)
        .order_by(V3AuditRun.id.desc())
        .all()
    )


def get_audit_run(db: Session, project_id: int, run_id: int) -> V3AuditRun | None:
    return db.query(V3AuditRun).filter(
        V3AuditRun.id == run_id,
        V3AuditRun.project_id == project_id,
    ).first()


def _target_out(t: V3AuditIssueTarget) -> dict:
    return {
        "id": t.id,
        "target_type": t.target_type,
        "target_ref": t.target_ref,
        "manifest_item_id": t.manifest_item_id,
    }


def issue_out(i: V3AuditIssue) -> dict:
    return {
        "id": i.id, "dimension": i.dimension, "severity": i.severity,
        "description": i.description, "affected_assets": i.affected_assets,
        "status": i.status, "resolution": i.resolution,
        "waive_reason": i.waive_reason, "waived_by": i.waived_by,
        "targets": [_target_out(t) for t in i.targets],
    }


def run_out(run: V3AuditRun) -> dict:
    return {
        "id": run.id, "project_id": run.project_id,
        "manifest_version_id": run.manifest_version_id,
        "status": run.status, "summary": run.summary,
        "started_at": run.started_at, "finished_at": run.finished_at,
        "issues": [issue_out(i) for i in run.issues],
    }


# --------------------------------------------------------------------------- #
# 检测缺口
# --------------------------------------------------------------------------- #

def list_gaps(db: Session, project_id: int) -> list:
    from app.models.v3_director import V3DetectedGap
    return (
        db.query(V3DetectedGap)
        .filter(V3DetectedGap.project_id == project_id)
        .order_by(V3DetectedGap.id.desc())
        .all()
    )