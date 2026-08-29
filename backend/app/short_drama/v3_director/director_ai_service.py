"""AI 导演服务：按用途分开的结构化生成 schema。

契约见实施计划第 9 轮：
- guidance / chat / proposal 三种用途，各自独立 schema，不使用通用 actions JSON
- AI 输出只能落入预定义操作类型白名单；未定义操作在解析层即被拒绝
- 项目级调用限额与冷却；AI 失败不阻塞业务流程
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import AIProviderConfig, V3ContextSnapshot
from app.short_drama.ai_service import AIResponseError, _endpoint, _json_content, decrypt_api_key

logger = logging.getLogger(__name__)

# 每项目每小时 AI 调用限额（含所有用途）
PROJECT_HOURLY_LIMIT = 30

# ---- 提案操作白名单（第 9 轮唯一入口；未定义操作一律拒绝）----
ACTION_TYPES: dict[str, dict[str, Any]] = {
    "update_anchor_controllable_vars": {
        "target_type": "character_anchor",
        "fields": {"expression", "pose", "costume", "styling", "lighting"},
        "desc": "更新角色锚点可控变量（不可变身份锚点禁止修改）",
    },
    "suggest_prop_state": {
        "target_type": "prop_anchor",
        "fields": {"wear_condition", "state_change"},
        "desc": "建议道具状态变化说明",
    },
    "suggest_continuity_resolution": {
        "target_type": "scene",
        "fields": {"change_from_previous", "resolution"},
        "desc": "为连续性问题建议处理说明",
    },
}

# 各用途的 system prompt + 输出 schema 约定
GUIDANCE_SCHEMA = {
    "suggestions": [
        {"kind": "gap|audit|stale|style", "title": "标题", "detail": "说明", "severity": "info|risk|blocker"}
    ]
}

PROPOSAL_SCHEMA = {
    "proposals": [
        {
            "action_type": "白名单中的类型",
            "target_type": "character_anchor|prop_anchor|scene",
            "target_ref": "CH-001 等",
            "title": "提案标题",
            "rationale": "理由",
            "changes": [{"field": "字段名", "before": "原值", "after": "新值"}],
            "impact_refs": ["受影响引用"],
        }
    ]
}


class DirectorAIError(ValueError):
    pass


class RateLimitError(DirectorAIError):
    pass


def _provider(db: Session, owner_id: int) -> AIProviderConfig | None:
    """AIProviderConfig 是全局共享配置（无 owner_id）：默认供应商优先，其次任意启用的。"""
    default = (
        db.query(AIProviderConfig)
        .filter(AIProviderConfig.enabled.is_(True), AIProviderConfig.is_default.is_(True))
        .first()
    )
    if default:
        return default
    return (
        db.query(AIProviderConfig)
        .filter(AIProviderConfig.enabled.is_(True))
        .order_by(AIProviderConfig.id.desc())
        .first()
    )


def check_rate_limit(db: Session, project_id: int) -> int:
    """项目级小时限额；返回剩余额度，超限抛 RateLimitError。"""
    from app.models import V3DirectorConversation, V3DirectorMessage

    hour_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
    used = (
        db.query(func.count(V3DirectorMessage.id))
        .join(V3DirectorConversation, V3DirectorConversation.id == V3DirectorMessage.conversation_id)
        .filter(
            V3DirectorConversation.project_id == project_id,
            V3DirectorMessage.created_at >= hour_ago,
        )
        .scalar() or 0
    )
    remaining = max(0, PROJECT_HOURLY_LIMIT - int(used))
    if remaining <= 0:
        raise RateLimitError("项目 AI 调用已达小时限额，请稍后再试")
    return remaining


def _call_llm(
    db: Session,
    owner_id: int,
    project_id: int,
    operation: str,
    system_prompt: str,
    user_prompt: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """调用 LLM；返回 (parsed_json, ai_meta)。所有调用都记录 AIGenerationRecord 审计日志。"""
    import time

    from app.short_drama.ai_service import record_ai_call

    config = _provider(db, owner_id)
    if not config:
        raise AIResponseError("未配置 AI 供应商")
    started = time.monotonic()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        import httpx

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
        ai_meta = {
            "model": config.model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "duration_ms": duration_ms,
        }
        try:
            parsed = _json_content(content)
        except AIResponseError:
            record_ai_call(
                db, owner_id=owner_id, project_id=project_id, operation=operation,
                model=config.model, status="invalid_json",
                request_snapshot={"messages": messages},
                response_snapshot={"invalid_content": str(content)[:20000]},
                input_tokens=input_tokens, output_tokens=output_tokens,
                duration_ms=duration_ms, provider_config_id=config.id,
            )
            raise
        record_ai_call(
            db, owner_id=owner_id, project_id=project_id, operation=operation,
            model=config.model, status="succeeded",
            request_snapshot={"messages": messages},
            response_snapshot={"content": parsed},
            input_tokens=input_tokens, output_tokens=output_tokens,
            duration_ms=duration_ms, provider_config_id=config.id,
        )
        return parsed, ai_meta
    except Exception as exc:
        record_ai_call(
            db, owner_id=owner_id, project_id=project_id, operation=operation,
            model=config.model, status="failed",
            request_snapshot={"messages": messages},
            input_tokens=0, output_tokens=0,
            duration_ms=round((time.monotonic() - started) * 1000),
            error=str(exc)[:4000], provider_config_id=config.id,
        )
        raise


def _system_prompt_for(purpose: str) -> str:
    base = "你是影视 AI 导演助理。只输出一个 JSON 对象，不使用 Markdown。"
    if purpose == "guidance":
        return (
            base + f"基于给定的项目上下文，输出建议列表，schema：{json.dumps(GUIDANCE_SCHEMA, ensure_ascii=False)}。"
            "suggestions 数量不超过 5 条，只基于上下文事实，不虚构。"
        )
    if purpose == "proposal":
        return (
            base + f"基于上下文生成操作提案，schema：{json.dumps(PROPOSAL_SCHEMA, ensure_ascii=False)}。"
            f"action_type 只能是：{', '.join(ACTION_TYPES)}。不得输出白名单以外的操作。"
        )
    return base + "根据对话历史和项目上下文回答，不虚构项目里没有的信息。"


def generate_guidance(db: Session, owner_id: int, snapshot: V3ContextSnapshot) -> dict[str, Any]:
    """生成右栏建议：缺失项、审计问题、stale 风险。返回结构化建议列表。"""
    check_rate_limit(db, snapshot.project_id)
    parsed, ai_meta = _call_llm(
        db, owner_id, snapshot.project_id, "director_guidance",
        _system_prompt_for("guidance"),
        f"项目上下文：\n{json.dumps(snapshot.content, ensure_ascii=False, indent=2)}",
    )
    suggestions = parsed.get("suggestions", [])
    if not isinstance(suggestions, list):
        suggestions = []
    cleaned = []
    for item in suggestions[:5]:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        cleaned.append({
            "kind": str(item.get("kind", "gap"))[:32],
            "title": str(item["title"])[:200],
            "detail": str(item.get("detail", ""))[:2000],
            "severity": item.get("severity", "info") if item.get("severity") in ("info", "risk", "blocker") else "info",
        })
    return {"suggestions": cleaned, "ai_meta": ai_meta, "revision_hash": snapshot.revision_hash}


def generate_chat_reply(
    db: Session,
    owner_id: int,
    snapshot: V3ContextSnapshot,
    history: list[dict[str, str]],
    user_message: str,
) -> tuple[str, dict[str, Any]]:
    """生成对话回复（纯文本回答，不产生操作）。"""
    check_rate_limit(db, snapshot.project_id)
    messages_text = "\n".join(f"{m['role']}: {m['content']}" for m in history[-20:])
    reply, ai_meta = _call_llm(
        db, owner_id, snapshot.project_id, "director_chat",
        _system_prompt_for("chat"),
        f"项目上下文：\n{json.dumps(snapshot.content, ensure_ascii=False, indent=2)}\n\n"
        f"对话历史：\n{messages_text}\n\n用户：{user_message}",
    )
    text = reply.get("reply") or reply.get("answer") or json.dumps(reply, ensure_ascii=False)
    return str(text)[:4000], ai_meta


def generate_proposals(db: Session, owner_id: int, snapshot: V3ContextSnapshot) -> list[dict[str, Any]]:
    """生成结构化提案；白名单外操作类型直接丢弃并记录日志。"""
    check_rate_limit(db, snapshot.project_id)
    parsed, _meta = _call_llm(
        db, owner_id, snapshot.project_id, "director_proposal",
        _system_prompt_for("proposal"),
        f"项目上下文（含可编辑目标）：\n{json.dumps(snapshot.content, ensure_ascii=False, indent=2)}",
    )
    raw_proposals = parsed.get("proposals", [])
    if not isinstance(raw_proposals, list):
        raw_proposals = []

    valid_targets = {t["ref"] for t in snapshot.content.get("editable_targets", [])}
    allowed = {
        spec["target_type"]: spec for spec in ACTION_TYPES.values()
    }
    cleaned: list[dict[str, Any]] = []
    for item in raw_proposals[:5]:
        if not isinstance(item, dict):
            continue
        action_type = str(item.get("action_type", ""))
        spec = ACTION_TYPES.get(action_type)
        if spec is None:
            # 未定义操作：解析层拒绝，绝不透传
            logger.warning("AI 提案使用了未定义操作类型 %s，已拒绝", action_type)
            continue
        target_type = str(item.get("target_type", ""))
        target_ref = str(item.get("target_ref", ""))
        if target_type != spec["target_type"] or target_ref not in valid_targets:
            continue
        changes = item.get("changes", [])
        if not isinstance(changes, list):
            continue
        cleaned_changes = []
        for change in changes:
            if not isinstance(change, dict):
                continue
            field = str(change.get("field", ""))
            if field not in spec["fields"]:
                continue
            cleaned_changes.append({
                "field": field,
                "before": str(change.get("before", ""))[:2000],
                "after": str(change.get("after", ""))[:2000],
            })
        if not cleaned_changes:
            continue
        cleaned.append({
            "action_type": action_type,
            "target_type": target_type,
            "target_ref": target_ref,
            "title": str(item.get("title", ""))[:200],
            "rationale": str(item.get("rationale", ""))[:2000],
            "changes": cleaned_changes,
            "impact_refs": [str(r)[:64] for r in (item.get("impact_refs") or []) if isinstance(r, (str, int))][:20],
        })
    return cleaned
