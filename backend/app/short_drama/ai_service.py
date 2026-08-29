"""AI provider configuration and OpenAI-compatible structured generation."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
try:  # Python 3.11+
    from datetime import UTC  # type: ignore[attr-defined]
except ImportError:  # Python 3.10 fallback
    from datetime import timezone as _tz
    UTC = _tz.utc  # type: ignore[assignment]
from datetime import datetime
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models import (
    AIProviderConfig, AIGenerationRecord, AIPromptTemplate, AdaptationCandidate, CreativeJob,
    Episode, NovelAnalysisVersion, ProjectBrief, Scene, ScreenplayRevisionCandidate,
    ShortDramaProject, SourceChapter, SourceDocument,
)
from app.schemas.short_drama import AIAdaptationIn, AIProviderInput, EpisodeAIGenerateIn, NovelAnalyzeIn
from app.short_drama import project_service, screenplay_service
from app.short_drama.director_rules import AI_RESPONSE_SCHEMAS, validate_schema


def _director_ledger_available() -> bool:
    from app.config import settings as _s
    return bool(getattr(_s, "v3_director_enabled", False))


class AIConfigurationError(ValueError): pass
class AIResponseError(ValueError): pass


PROMPTS = {
    "novel_chunk_analysis": (
        "小说分块分析", "你是专业短剧编剧分析师。只输出一个 JSON 对象，不使用 Markdown。不得虚构原文没有的信息。",
        "分析下面的小说原文，输出 synopsis、premise、opening_hook、characters、locations、events、beats、timeline、conflicts、hooks、facts、relationship_graph、worldview_bounds、load_bearing_scenes、continuity_facts、adaptation_risks、source_references。"
        "beats 需包含事件、目标、阻碍、升级、转折、结果、情绪强度和来源定位；所有检查结论仅作为建议。characters/locations/events 均为数组；source_references 使用 chapter_number、paragraph_start、paragraph_end。\n\n{content}",
    ),
    "novel_analysis_merge": (
        "小说分析合并", "你是故事编辑。只输出一个 JSON 对象，合并重复实体，保留来源引用，不得增加输入中没有的事实。",
        "合并以下分块分析，输出 synopsis、premise、opening_hook、structure、core_conflict、characters、locations、events、beats、timeline、hooks、emotional_beats、relationship_graph、worldview_bounds、load_bearing_scenes、continuity_facts、adaptation_risks、facts、source_references。保留证据来源，不把推断伪装成原文事实。\n\n{content}",
    ),
    "novel_adaptation": (
        "小说改编方案", "你是短剧总编剧。只输出 JSON，严格保持可追溯性，不得改变故事核心事实。",
        "根据故事档案和创作简报生成改编候选。输出一个 JSON 对象，根节点包含 options 数组字段。每个方案必须包含 key、label、description、metrics、episodes。"
        "每集包含 title、synopsis、target_duration、scenes；场景包含 heading、location_name、time_of_day、interior_exterior、content、elements、source_references、purpose、target_duration。"
        "elements 是对象数组，每个元素包含 type 和 text 两个字段，type 只能是 action/dialogue/narration/transition 之一。"
        "source_references 是对象数组，每个元素包含 document_id、chapter_number、paragraph_start、paragraph_end 四个字段；"
        "当前文档 ID 为 {document_id}，章节结构（章节号:段落数）为 {chapters}。引用原文时 document_id 必须等于 {document_id}，chapter_number 必须是章节结构里存在的章节号；"
        "如果场景没有明确的原文出处，source_references 可以为空数组。"
        "只生成这些策略：{strategies}。目标 {episode_count} 集。\n\n故事档案：{analysis}\n\n创作简报：{brief}",
    ),
    "episode_screenplay": (
        "单集剧本生成", "你是短剧分集编剧。只输出一个 JSON 对象。保留已确定的人物事实和原文引用，不得虚构不存在的来源。",
        "为指定分集生成可拍摄的结构化剧本候选。根对象包含 title、synopsis、premise、gate_report、dialogue_diagnostics、core_conflict、emotional_arc、opening_hook、ending_hook、target_duration、scenes。"
        "每个场景包含 heading、location_name、time_of_day、interior_exterior、content、elements、source_references、purpose、target_duration；"
        "elements 类型只能是 action/dialogue/narration/transition，对白可包含 speaker。总场景时长应接近单集目标时长。\n\n"
        "项目简报：{brief}\n故事档案：{analysis}\n当前分集：{episode}\n人工要求：{instruction}",
    ),
    "script_manifest": (
        "单集拍摄清单", "你是专业漫剧导演、选角师与分镜师。只输出一个合法 JSON 对象，不使用 Markdown，不省略对白、动作任务、旁白、镜头备注及视觉一致性要求。所有实体必须输出为对象，禁止用字符串代替对象。",
        "将输入剧本转换为可直接用于角色定妆、场景设计、道具设计和逐镜头生成的完整拍摄清单。\n"
        "根对象必须包含：story_summary、characters、locations、props、scenes。\n"
        "characters 每项必须包含 stable_key（CH-001 递增）、name、gender、identity、age_appearance、core_identity、facial_features、hairstyle、clothing、pose_expression、technical_style、negative_constraints、description、visual_prompt。\n"
        "角色 visual_prompt 只能包含以下六段，必须按此顺序和英文标题输出：1.Core Identity、2.Facial Features、3.Hairstyle、4.Clothing、5.Pose&Expression、6.Technical Quality。"
        "Core Identity 只写种族/地域外观、性别、年龄段、体型、职业或稳定身份特征；禁止写剧情作用、人物关系、性格、经历和故事摘要。"
        "Pose&Expression 默认固定为“白色背景，正面全身照”，除非人工明确提出其他定妆姿态。"
        "Technical Quality 只写画质、媒介与美术风格。visual_prompt 不得包含上述六段之外的内容。\n"
        "locations 每项必须包含 stable_key（LOC-001 递增）、name、description、sub_locations、spatial_layout、time_weather、lighting、color_palette、fixed_objects、visual_prompt。\n"
        "props 每项必须包含 stable_key（PROP-001 递增）、name、category、description、appearance、owner_character_name、appearance_scope、continuity_note、visual_prompt、critical。\n"
        "scenes 每项必须包含 scene_no、heading、location_name、sub_location、time_of_day、interior_exterior、rhythm、emotion、atmosphere、content、character_names、prop_names、shots。\n"
        "shots 每项必须包含 shot_no、title、purpose、visual_description、action、expression、dialogue、narration、inner_monologue、character_names、prop_names、mood、shot_size、camera_angle、camera_movement、composition、transition、duration、prompt。\n"
        "shot.prompt 必须包含 original、override、effective 三个对象；original 和 effective 均包含 base_visual、visual_style、camera_movement、composition_guide、initial_frame、character_consistency、negative_constraints；首次生成时 override 为空对象，effective 与 original 相同。\n"
        "每个 character_names、location_name、prop_names 引用必须能在根级实体列表按 name 找到；场号、镜号在各自范围内唯一且按叙事顺序排列；duration 使用秒。"
        "制作建议：每个 shots 项可作为独立视频生成组，建议单组不超过 15 秒；该建议不得删减用户内容，也不得阻止后续确认或生成。"
        "当目标时长为 180 秒时，建议规划 14～15 个生成组；这只是可忽略的制作建议。"
        "若 mode=storyboard，严格保持原分镜顺序、对白、动作任务与镜头备注，只补全缺失字段；若 mode=novel，先理解故事结构，再按节奏拆分为可拍摄镜头。"
        "不得虚构剧情事实；视觉设计可以在不改变剧情的前提下补全。目标设置：{settings}\n创作模式：{mode}\n剧本：\n{content}",
    ),
    "json_repair": (
        "JSON 修复", "你是 JSON 修复器。只输出修复后的 JSON，不解释，不改变语义。",
        "以下模型输出无法解析为 JSON，请修复：\n\n{content}",
    ),
    "director_story_ledger": (
        "导演故事台账生成", "你是前期导演分析师。只输出一个 JSON 对象，严格保持可追溯性，不得虚构原文没有的信息。每个节拍必须有稳定键、来源定位和证据等级。",
        "根据故事档案构建剧本台账（beat sheet）。根对象包含 name、summary、beats 数组和 decisions 数组。\n"
        "每个 beat 必须包含：stable_key（格式 BT-001 递增）、order（从 1 开始）、event（事件）、goal（目标）、conflict（冲突）、"
        "reversal（反转）、outcome（结果）、causal_dependency（依赖的前序 BT 键，可为 null）、characters（参与角色名数组）、"
        "emotion_intensity（情绪强度 0-10 数字）、emotion_valence（效价 -5~+5 数字，负面为负值）、dominant_emotion（主导情绪）、"
        "narrative_function（叙事功能：setup/escalation/climax/resolution/breather 等短语）、evidence_type（explicit=原文明确/inferred=推断/assumed=假设）、"
        "confidence（仅 assumed 需要，0-1 数字）、source_locator（章节/段落定位，如\"第3章 第12段\"）。\n"
        "decisions 数组记录源材料中的矛盾：question（矛盾描述）、options（可选处理方式字符串数组）。\n\n故事档案：{analysis}",
    ),
    "guidance": (
        "AI 导演建议", "你是影视 AI 导演助理。基于给定的项目上下文，输出建议列表，只输出一个 JSON 对象。",
        '建议 schema：{"suggestions":[{"kind":"gap|audit|stale|style","title":"标题","detail":"说明","severity":"info|risk|blocker"}]}。'
        "suggestions 数量不超过 5 条，只基于上下文事实，不虚构。\n\n项目上下文：{content}",
    ),
    "proposal": (
        "AI 提案生成", "你是影视 AI 导演助理。基于上下文生成操作提案，只输出一个 JSON 对象。",
        '提案 schema：{"proposals":[{"action_type":"update_anchor_controllable_vars|suggest_prop_state|suggest_continuity_resolution",'
        '"target_type":"character_anchor|prop_anchor|scene","target_ref":"CH-001 等",'
        '"title":"提案标题","rationale":"理由","changes":[{"field":"字段名","before":"原值","after":"新值"}],'
        '"impact_refs":["受影响引用"]}]}。action_type 只能是白名单中的类型，不得输出白名单以外的操作。\n\n项目上下文：{content}',
    ),
}


def _now() -> datetime: return datetime.now(UTC).replace(tzinfo=None)


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_api_key(value: str) -> str: return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_api_key(value: str) -> str:
    try: return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc: raise AIConfigurationError("AI API Key 无法解密，请重新保存配置") from exc


def _hint(value: str) -> str:
    if not value: return "未设置"
    return f"{value[:3]}***{value[-4:]}" if len(value) > 8 else "***"


def record_ai_call(
    db: Session,
    *,
    owner_id: int,
    project_id: int | None,
    operation: str,
    model: str,
    status: str,
    request_snapshot: dict[str, Any] | None = None,
    response_snapshot: dict[str, Any] | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
    estimated_cost: float = 0.0,
    duration_ms: int = 0,
    error: str | None = None,
    provider_config_id: int | None = None,
) -> AIGenerationRecord:
    """统一记录一次 AI 调用的审计日志（供所有 LLM 调用路径复用）。"""
    record = AIGenerationRecord(
        owner_id=owner_id,
        project_id=project_id,
        provider_config_id=provider_config_id,
        operation=operation,
        model=model,
        status=status,
        request_snapshot=request_snapshot or {},
        response_snapshot=response_snapshot or {},
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens or input_tokens + output_tokens,
        estimated_cost=estimated_cost,
        duration_ms=duration_ms,
        error=error,
        finished_at=_now() if status in ("succeeded", "failed", "invalid_json") else None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def save_provider(db: Session, actor_id: int, body: AIProviderInput, provider_id: int | None = None) -> AIProviderConfig:
    item = db.get(AIProviderConfig, provider_id) if provider_id else AIProviderConfig(created_by=actor_id, api_key_encrypted="")
    if provider_id and not item: raise project_service.ProjectNotFoundError("AI 服务商配置不存在")
    if not provider_id: db.add(item)
    for field in ("name", "provider", "base_url", "model", "enabled", "is_default", "timeout_seconds", "max_tokens"):
        setattr(item, field, getattr(body, field))
    if body.api_key is not None:
        item.api_key_encrypted = encrypt_api_key(body.api_key); item.api_key_hint = _hint(body.api_key)
    elif not provider_id:
        raise AIConfigurationError("新建服务商必须填写 API Key；本地免密接口可填写占位值")
    if item.is_default:
        db.query(AIProviderConfig).filter(AIProviderConfig.id != item.id).update({AIProviderConfig.is_default: False}, synchronize_session=False)
    db.commit(); db.refresh(item); return item


def delete_provider(db: Session, provider_id: int) -> None:
    item = db.get(AIProviderConfig, provider_id)
    if not item: raise project_service.ProjectNotFoundError("AI 服务商配置不存在")
    if db.query(CreativeJob.id).filter(CreativeJob.provider_config_id == item.id).first():
        item.enabled = False; item.is_default = False
    else: db.delete(item)
    db.commit()


def provider(db: Session, provider_id: int | None) -> AIProviderConfig:
    item = db.get(AIProviderConfig, provider_id) if provider_id else db.query(AIProviderConfig).filter(AIProviderConfig.enabled.is_(True), AIProviderConfig.is_default.is_(True)).first()
    if not item or not item.enabled: raise AIConfigurationError("没有可用的 AI 服务商，请管理员先完成模型配置")
    return item


def seed_prompts(db: Session) -> None:
    for code, (name, system_prompt, user_prompt) in PROMPTS.items():
        v1 = db.query(AIPromptTemplate).filter(AIPromptTemplate.code == code, AIPromptTemplate.version == 1).first()
        if not v1:
            db.add(AIPromptTemplate(code=code, name=name, version=1, system_prompt=system_prompt, user_prompt=user_prompt, response_schema=AI_RESPONSE_SCHEMAS.get(code, {}), enabled=True))
        else:
            # 同步内置 v1 模板内容（用户编辑走 v2+，不会覆盖用户的自定义版本）
            if v1.system_prompt != system_prompt or v1.user_prompt != user_prompt:
                v1.system_prompt = system_prompt
                v1.user_prompt = user_prompt
                v1.name = name
            schema = AI_RESPONSE_SCHEMAS.get(code, {})
            if schema and v1.response_schema != schema:
                v1.response_schema = schema
    db.commit()


def prompt_template(db: Session, code: str) -> AIPromptTemplate:
    item = db.query(AIPromptTemplate).filter(AIPromptTemplate.code == code, AIPromptTemplate.enabled.is_(True)).order_by(AIPromptTemplate.version.desc()).first()
    if not item: raise AIConfigurationError(f"AI 提示词模板不存在：{code}")
    return item


def _json_content(value: str) -> dict[str, Any]:
    text = value.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I); text = re.sub(r"\s*```$", "", text)
    # 1) 直接解析
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    # 2) 从文本提取 JSON：优先按更靠前的起始符判断结构（对象 vs 数组）
    if data is None:
        obj_start = text.find("{")
        arr_start = text.find("[")
        if obj_start >= 0 and (arr_start < 0 or obj_start < arr_start):
            end = text.rfind("}")
            if end > obj_start:
                try:
                    data = json.loads(text[obj_start:end + 1])
                except json.JSONDecodeError:
                    data = None
        elif arr_start >= 0:
            end = text.rfind("]")
            if end > arr_start:
                try:
                    data = json.loads(text[arr_start:end + 1])
                except json.JSONDecodeError as exc:
                    raise AIResponseError(f"模型 JSON 解析失败：{exc.msg}") from exc
    if data is None:
        raise AIResponseError("模型没有返回 JSON 对象")
    # 数组根节点 → 包装为 {"options": [...]}（novel_adaptation 语义）
    if isinstance(data, list):
        data = {"options": data}
    if not isinstance(data, dict):
        raise AIResponseError("模型返回的 JSON 根节点必须是对象")
    return data


def _endpoint(base_url: str) -> str:
    value = base_url.rstrip("/")
    return value if value.endswith("/chat/completions") else f"{value}/chat/completions"


def complete_json(db: Session, job: CreativeJob, operation: str, template_code: str, variables: dict[str, Any], *, repair: bool = True) -> tuple[dict[str, Any], AIGenerationRecord]:
    config = provider(db, job.provider_config_id); template = prompt_template(db, template_code)
    user_prompt = template.user_prompt.format(**{key: value if isinstance(value, str) else json.dumps(value, ensure_ascii=False) for key, value in variables.items()})
    messages = [{"role": "system", "content": template.system_prompt}, {"role": "user", "content": user_prompt}]
    record = AIGenerationRecord(owner_id=job.owner_id, project_id=job.project_id, job_id=job.id, provider_config_id=config.id, prompt_template_id=template.id, operation=operation, model=config.model, request_snapshot={"messages": messages, "temperature": 0.2}, status="running")
    db.add(record); db.flush(); job.provider_config_id=config.id; job.prompt_template_id=template.id; job.model=config.model; db.commit()
    started = time.monotonic()
    try:
        response = httpx.post(_endpoint(config.base_url), headers={"Authorization": f"Bearer {decrypt_api_key(config.api_key_encrypted)}", "Content-Type": "application/json"}, json={"model": config.model, "messages": messages, "temperature": 0.2, "max_tokens": config.max_tokens, "response_format": {"type": "json_object"}}, timeout=config.timeout_seconds)
        response.raise_for_status(); payload = response.json(); content = payload["choices"][0]["message"]["content"]
        usage = payload.get("usage") or {}; record.input_tokens=int(usage.get("prompt_tokens") or 0); record.output_tokens=int(usage.get("completion_tokens") or 0); record.total_tokens=int(usage.get("total_tokens") or record.input_tokens+record.output_tokens)
        try: parsed = _json_content(content)
        except AIResponseError:
            if not repair or template_code == "json_repair": raise
            record.response_snapshot={"invalid_content":str(content)[:20000]};record.status="invalid_json";record.duration_ms=round((time.monotonic()-started)*1000);record.finished_at=_now();db.commit()
            return complete_json(db, job, f"{operation}.repair", "json_repair", {"content": content}, repair=False)
        raw_issues = validate_schema(parsed, template.response_schema or {}) if template.response_schema else []
        if raw_issues:
            parsed.setdefault("_analysis_meta", {})["raw_validation_errors"] = raw_issues
        record.response_snapshot={"content": parsed, "raw_validation_errors": raw_issues}; record.status="succeeded"; record.duration_ms=round((time.monotonic()-started)*1000); record.finished_at=_now(); db.commit(); db.refresh(record)
        return parsed, record
    except Exception as exc:
        record.status="failed"; record.error=str(exc)[:4000]; record.duration_ms=round((time.monotonic()-started)*1000); record.finished_at=_now(); db.commit()
        raise AIResponseError(str(exc)) from exc


def create_story_ledger_job(db: Session, owner_id: int, project_id: int, analysis_id: int, idempotency_key: str, provider_config_id: int | None = None) -> CreativeJob:
    """V3 故事台账生成任务（需要 v3_director_enabled）。"""
    seed_prompts(db)
    if not _director_ledger_available():
        raise AIConfigurationError("导演前期模块未启用")
    project_service.owned_project(db, owner_id, project_id)
    analysis = db.query(NovelAnalysisVersion).filter(
        NovelAnalysisVersion.id == analysis_id,
        NovelAnalysisVersion.owner_id == owner_id,
        NovelAnalysisVersion.project_id == project_id,
    ).first()
    if not analysis:
        raise AIConfigurationError("小说分析版本不存在")
    config = provider(db, provider_config_id)
    key = f"v3-ledger:{project_id}:{analysis.id}:{idempotency_key}"
    existing = db.query(CreativeJob).filter(CreativeJob.owner_id == owner_id, CreativeJob.idempotency_key == key).first()
    if existing:
        return existing
    job = CreativeJob(
        owner_id=owner_id, project_id=project_id, job_type="director_story_ledger", status="queued", progress=0,
        idempotency_key=key, provider_config_id=config.id, input_payload={"analysis_id": analysis.id}, logs=[],
    )
    db.add(job); db.commit(); db.refresh(job); return job


def test_provider(db: Session, provider_id: int) -> dict[str, Any]:
    config = provider(db, provider_id); started=time.monotonic()
    response=httpx.post(_endpoint(config.base_url), headers={"Authorization":f"Bearer {decrypt_api_key(config.api_key_encrypted)}","Content-Type":"application/json"}, json={"model":config.model,"messages":[{"role":"user","content":"只回复 OK"}],"max_tokens":8,"temperature":0}, timeout=config.timeout_seconds)
    response.raise_for_status()
    return {"ok": True, "model": config.model, "latency_ms": round((time.monotonic()-started)*1000)}


def create_analysis_job(db: Session, owner_id: int, project_id: int, body: NovelAnalyzeIn) -> CreativeJob:
    seed_prompts(db)
    project_service.owned_project(db, owner_id, project_id); screenplay_service._owned_document(db, owner_id, project_id, body.document_id)
    if body.chapter_start > body.chapter_end: raise AIConfigurationError("起始章节不能大于结束章节")
    config=provider(db, body.provider_config_id); key=f"ai-analysis:{project_id}:{body.document_id}:{body.chapter_start}-{body.chapter_end}:{body.idempotency_key}"
    existing=db.query(CreativeJob).filter(CreativeJob.owner_id==owner_id,CreativeJob.idempotency_key==key).first()
    if existing:return existing
    job=CreativeJob(owner_id=owner_id,project_id=project_id,job_type="analyze_novel",status="queued",progress=0,idempotency_key=key,provider_config_id=config.id,input_payload=body.model_dump(),logs=[])
    db.add(job);db.commit();db.refresh(job);return job


def create_adaptation_job(db: Session, owner_id: int, project_id: int, body: AIAdaptationIn) -> CreativeJob:
    seed_prompts(db)
    project_service.owned_project(db, owner_id, project_id); analysis=db.query(NovelAnalysisVersion).filter(NovelAnalysisVersion.id==body.analysis_id,NovelAnalysisVersion.owner_id==owner_id,NovelAnalysisVersion.project_id==project_id).first()
    if not analysis: raise project_service.ProjectNotFoundError("小说分析版本不存在")
    config=provider(db, body.provider_config_id); key=f"ai-adaptation:{project_id}:{analysis.id}:{body.idempotency_key}"
    existing=db.query(CreativeJob).filter(CreativeJob.owner_id==owner_id,CreativeJob.idempotency_key==key).first()
    if existing:return existing
    job=CreativeJob(owner_id=owner_id,project_id=project_id,job_type="generate_adaptation",status="queued",progress=0,idempotency_key=key,provider_config_id=config.id,input_payload=body.model_dump(),logs=[])
    db.add(job);db.commit();db.refresh(job);return job


def create_episode_screenplay_job(db: Session, owner_id: int, project_id: int, episode_id: int, body: EpisodeAIGenerateIn) -> CreativeJob:
    seed_prompts(db)
    project_service.owned_project(db, owner_id, project_id)
    episode = screenplay_service._owned_episode(db, owner_id, project_id, episode_id)
    if episode.is_locked:
        raise AIConfigurationError("分集已锁定，请先解锁后再生成")
    config = provider(db, body.provider_config_id)
    key = f"ai-episode:{project_id}:{episode_id}:{body.idempotency_key}"
    existing = db.query(CreativeJob).filter(CreativeJob.owner_id == owner_id, CreativeJob.idempotency_key == key).first()
    if existing:
        return existing
    job = CreativeJob(
        owner_id=owner_id, project_id=project_id, job_type="generate_episode_screenplay", status="queued", progress=0,
        idempotency_key=key, provider_config_id=config.id,
        input_payload={**body.model_dump(), "episode_id": episode_id, "base_lock_version": episode.lock_version}, logs=[],
    )
    db.add(job); db.commit(); db.refresh(job); return job


def create_script_manifest_job(db: Session, owner_id: int, project_id: int, episode_id: int, *, provider_config_id: int, idempotency_key: str) -> CreativeJob:
    """Queue the potentially long manifest LLM call outside the HTTP request."""
    from app.short_drama import phase1_service

    seed_prompts(db)
    script = phase1_service.get_script(db, owner_id, project_id, episode_id)
    if not str(script["text"]).strip():
        raise AIConfigurationError("请先填写并保存剧本内容")
    config = provider(db, provider_config_id)
    key = f"script-manifest:{project_id}:{episode_id}:{idempotency_key}"
    existing = db.query(CreativeJob).filter(CreativeJob.owner_id == owner_id, CreativeJob.idempotency_key == key).first()
    if existing:
        return existing
    job = CreativeJob(
        owner_id=owner_id, project_id=project_id, job_type="generate_script_manifest", status="queued", progress=0,
        idempotency_key=key, provider_config_id=config.id,
        input_payload={"episode_id": episode_id, "script_revision": script["script_revision"]}, logs=[],
    )
    db.add(job); db.commit(); db.refresh(job); return job


def completed_local_job(db: Session, owner_id: int, project_id: int, episode_id: int, idempotency_key: str, manifest_id: int) -> CreativeJob:
    key = f"script-manifest-local:{project_id}:{episode_id}:{idempotency_key}"
    existing = db.query(CreativeJob).filter(CreativeJob.owner_id == owner_id, CreativeJob.idempotency_key == key).first()
    if existing:
        return existing
    job = CreativeJob(
        owner_id=owner_id, project_id=project_id, job_type="generate_script_manifest", status="succeeded", progress=100,
        idempotency_key=key, input_payload={"episode_id": episode_id},
        output_payload={"manifest_id": manifest_id, "episode_id": episode_id}, logs=[],
        started_at=_now(), finished_at=_now(), heartbeat_at=_now(),
    )
    db.add(job); db.commit(); db.refresh(job); return job


def _episode_candidate_errors(content: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = list((content.get("_analysis_meta") or {}).get("raw_validation_errors") or [])
    for field in ("title", "synopsis", "core_conflict", "opening_hook", "ending_hook"):
        if not str(content.get(field, "")).strip():
            errors.append({"path": field, "message": f"缺少分集字段：{field}"})
    scenes = content.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        return [*errors, {"path": "scenes", "message": "单集至少需要一个场景"}]
    for scene_index, scene in enumerate(scenes):
        if not isinstance(scene, dict) or not str(scene.get("heading", "")).strip():
            errors.append({"path": f"scenes[{scene_index}].heading", "message": "场景标题不能为空"})
            continue
        elements = scene.get("elements", [])
        if not isinstance(elements, list):
            errors.append({"path": f"scenes[{scene_index}].elements", "message": "剧本元素必须是数组"})
            continue
        for element_index, element in enumerate(elements):
            if not isinstance(element, dict) or element.get("type") not in screenplay_service.ELEMENT_TYPES or not str(element.get("text", "")).strip():
                errors.append({"path": f"scenes[{scene_index}].elements[{element_index}]", "message": "剧本元素类型或文本无效"})
    return errors


def list_episode_candidates(db: Session, owner_id: int, project_id: int, episode_id: int) -> list[ScreenplayRevisionCandidate]:
    screenplay_service._owned_episode(db, owner_id, project_id, episode_id)
    return db.query(ScreenplayRevisionCandidate).filter(
        ScreenplayRevisionCandidate.owner_id == owner_id,
        ScreenplayRevisionCandidate.project_id == project_id,
        ScreenplayRevisionCandidate.episode_id == episode_id,
    ).order_by(ScreenplayRevisionCandidate.id.desc()).all()


def confirm_episode_candidate(db: Session, owner_id: int, project_id: int, episode_id: int, candidate_id: int):
    project = project_service.owned_project(db, owner_id, project_id)
    episode = screenplay_service._owned_episode(db, owner_id, project_id, episode_id)
    candidate = db.query(ScreenplayRevisionCandidate).filter(
        ScreenplayRevisionCandidate.id == candidate_id,
        ScreenplayRevisionCandidate.owner_id == owner_id,
        ScreenplayRevisionCandidate.project_id == project_id,
        ScreenplayRevisionCandidate.episode_id == episode_id,
    ).first()
    if not candidate:
        raise project_service.ProjectNotFoundError("单集剧本候选不存在")
    if candidate.status == "confirmed" and candidate.confirmed_version_id:
        return screenplay_service.owned_version(db, owner_id, project_id, candidate.confirmed_version_id)
    if candidate.status != "pending":
        raise AIConfigurationError("候选剧本校验未通过，不能应用")
    if episode.is_locked:
        raise project_service.ProjectConflictError("分集已锁定，不能应用 AI 候选")
    if episode.lock_version != candidate.base_lock_version:
        raise project_service.ProjectConflictError("分集在 AI 生成后已被修改，请重新生成候选")
    content = candidate.content
    db.query(Scene).filter(Scene.episode_id == episode.id).delete(synchronize_session=False)
    for index, payload in enumerate(content.get("scenes", []), start=1):
        db.add(Scene(
            owner_id=owner_id, episode_id=episode.id, scene_no=f"{episode.number}-{index}", sort_order=index, status="draft",
            heading=str(payload.get("heading", f"场景 {index}"))[:255], location_name=str(payload.get("location_name", ""))[:160],
            time_of_day=str(payload.get("time_of_day", ""))[:64], interior_exterior=str(payload.get("interior_exterior", ""))[:16],
            content=str(payload.get("content", "")), elements=list(payload.get("elements", [])),
            source_references=list(payload.get("source_references", [])), purpose=str(payload.get("purpose", "")),
            target_duration=max(0, int(payload.get("target_duration", 0))), character_ids=[],
        ))
    for field in ("title", "synopsis", "core_conflict", "emotional_arc", "opening_hook", "ending_hook", "target_duration"):
        if field in content:
            setattr(episode, field, content[field])
    episode.lock_version += 1
    db.flush(); db.expire_all()
    episodes = db.query(Episode).options(selectinload(Episode.scenes)).filter(Episode.project_id == project_id, Episode.owner_id == owner_id).order_by(Episode.sort_order).all()
    current = db.query(screenplay_service.StoryVersion).filter(screenplay_service.StoryVersion.project_id == project_id, screenplay_service.StoryVersion.is_current.is_(True)).first()
    version = screenplay_service._create_version(db, project, f"AI 单集剧本 · 第 {episode.number} 集", "ai_episode", {"episodes": screenplay_service._serialize_episodes(episodes), "candidate_id": candidate.id}, current.id if current else None)
    candidate.status = "confirmed"; candidate.confirmed_version_id = version.id; candidate.confirmed_at = _now()
    db.query(ScreenplayRevisionCandidate).filter(ScreenplayRevisionCandidate.episode_id == episode_id, ScreenplayRevisionCandidate.id != candidate.id, ScreenplayRevisionCandidate.status == "pending").update({ScreenplayRevisionCandidate.status: "superseded"}, synchronize_session=False)
    db.commit(); db.refresh(version); return version


def _source_chunks(document: SourceDocument, chapter_start: int, chapter_end: int, max_chars: int = 12000) -> list[str]:
    chunks: list[str] = []; current: list[str] = []; size = 0
    chapters = [item for item in document.chapters if chapter_start <= item.number <= chapter_end]
    for chapter in chapters:
        for paragraph in chapter.paragraphs:
            line = f"[第{chapter.number}章 第{paragraph.paragraph_index}段] {paragraph.text}"
            if current and size + len(line) > max_chars:
                chunks.append("\n".join(current)); current=[]; size=0
            current.append(line); size += len(line) + 1
    if current: chunks.append("\n".join(current))
    return chunks


def _analysis_errors(content: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = list((content.get("_analysis_meta") or {}).get("raw_validation_errors") or [])
    for field in ("synopsis", "characters", "locations", "events"):
        if field not in content: errors.append({"path": field, "message": f"缺少故事档案字段：{field}"})
    for field in ("characters", "locations", "events", "timeline", "hooks", "facts", "source_references"):
        if field in content and not isinstance(content[field], list): errors.append({"path": field, "message": f"{field} 必须是数组"})
    return errors


def _finish_ai_job(db: Session, job: CreativeJob, output: dict[str, Any]) -> None:
    records=db.query(AIGenerationRecord).filter(AIGenerationRecord.job_id==job.id).all()
    input_tokens=sum(item.input_tokens for item in records);output_tokens=sum(item.output_tokens for item in records)
    job.status="succeeded";job.progress=100;job.output_payload=output;job.token_usage={"input_tokens":input_tokens,"output_tokens":output_tokens,"total_tokens":input_tokens+output_tokens};job.finished_at=_now();job.heartbeat_at=_now();db.commit()


def process_ai_job(db: Session, job: CreativeJob, progress) -> None:
    if job.job_type == "generate_script_manifest":
        from app.short_drama import phase1_service

        episode_id = int(job.input_payload["episode_id"])
        script = phase1_service.get_script(db, job.owner_id, int(job.project_id), episode_id)
        if script["script_revision"] != int(job.input_payload["script_revision"]):
            raise AIResponseError("剧本在任务提交后已修改，请重新生成拍摄清单")
        if not progress(db, job, 20, "AI 正在分析剧本结构、场景与角色"): return
        content, _ = complete_json(db, job, "script_manifest", "script_manifest", {
            "mode": script["mode"], "settings": script["settings"], "content": script["text"],
        })
        if not progress(db, job, 85, "正在校验镜头顺序和素材清单"): return
        manifest = phase1_service.generate_manifest(db, job.owner_id, int(job.project_id), episode_id, content)
        _finish_ai_job(db, job, {"manifest_id": manifest.id, "episode_id": episode_id, "version": manifest.version}); return
    if job.job_type == "analyze_novel":
        document=screenplay_service._owned_document(db,job.owner_id,int(job.project_id),int(job.input_payload["document_id"]))
        start=int(job.input_payload["chapter_start"]);end=int(job.input_payload["chapter_end"]);chunks=_source_chunks(document,start,end)
        if not chunks: raise AIResponseError("选择范围内没有可分析的小说内容")
        analyses=[];last_record=None
        for index,chunk in enumerate(chunks,start=1):
            if not progress(db,job,10+round(index/max(1,len(chunks))*55),f"AI 正在分析第 {index}/{len(chunks)} 个文本块"): return
            result,last_record=complete_json(db,job,"novel_chunk_analysis","novel_chunk_analysis",{"content":chunk});analyses.append(result)
        if len(analyses)>1:
            if not progress(db,job,75,"正在合并人物、事件和时间线"): return
            content,last_record=complete_json(db,job,"novel_analysis_merge","novel_analysis_merge",{"content":analyses})
        else: content=analyses[0]
        errors=_analysis_errors(content);version=(db.query(func.max(NovelAnalysisVersion.version)).filter(NovelAnalysisVersion.project_id==job.project_id,NovelAnalysisVersion.document_id==document.id).scalar() or 0)+1
        analysis=NovelAnalysisVersion(owner_id=job.owner_id,project_id=int(job.project_id),document_id=document.id,generation_record_id=last_record.id if last_record else None,version=version,status="candidate",chapter_start=start,chapter_end=end,content=content,validation_errors=errors)
        db.add(analysis);db.flush();_finish_ai_job(db,job,{"analysis_id":analysis.id,"version":version,"validation_errors":errors});return
    if job.job_type == "generate_adaptation":
        analysis=db.query(NovelAnalysisVersion).filter(NovelAnalysisVersion.id==int(job.input_payload["analysis_id"]),NovelAnalysisVersion.owner_id==job.owner_id).first()
        if not analysis: raise AIResponseError("小说分析版本不存在")
        project=project_service.owned_project(db,job.owner_id,int(job.project_id));brief=project.brief
        count=int(job.input_payload.get("episode_count") or (brief.episode_count if brief else 1));strategies=job.input_payload.get("strategies") or ["faithful","high_tempo","emotional"]
        document=screenplay_service._owned_document(db,job.owner_id,int(job.project_id),analysis.document_id)
        # 提供真实文档 ID 和章节结构给 LLM，避免它编造 source_references
        chapters_info = {chapter.number: len(chapter.paragraphs) for chapter in document.chapters}
        if not progress(db,job,20,"AI 正在设计改编策略和分集结构"): return
        result,_=complete_json(db,job,"novel_adaptation","novel_adaptation",{
            "analysis":analysis.content,
            "brief":{"genre":brief.genre if brief else "","audience":brief.audience if brief else "","tone":brief.tone if brief else "","platform":brief.platform if brief else "","episode_duration":brief.episode_duration if brief else 60,"visual_style":brief.visual_style if brief else ""},
            "strategies":",".join(strategies),
            "episode_count":count,
            "document_id":document.id,
            "chapters":json.dumps(chapters_info, ensure_ascii=False),
        })
        options=result.get("options")
        if not isinstance(options,list) or not options: raise AIResponseError("模型没有返回改编方案")
        errors=[{"option":option.get("key","unknown"),**error} for option in options if isinstance(option,dict) for error in screenplay_service._validate_option(option,document)]
        candidate=AdaptationCandidate(owner_id=job.owner_id,project_id=int(job.project_id),document_id=document.id,chapter_start=analysis.chapter_start,chapter_end=analysis.chapter_end,status="pending",options=options,validation_errors=errors)
        db.add(candidate);db.flush();_finish_ai_job(db,job,{"candidate_id":candidate.id,"analysis_id":analysis.id,"option_count":len(options),"validation_errors":errors});return
    if job.job_type == "generate_episode_screenplay":
        project = project_service.owned_project(db, job.owner_id, int(job.project_id))
        episode = screenplay_service._owned_episode(db, job.owner_id, int(job.project_id), int(job.input_payload["episode_id"]))
        if episode.is_locked:
            raise AIResponseError("分集已锁定，AI 任务已停止")
        if episode.lock_version != int(job.input_payload["base_lock_version"]):
            raise AIResponseError("分集内容已发生变化，请重新发起生成")
        analysis = db.query(NovelAnalysisVersion).filter(
            NovelAnalysisVersion.owner_id == job.owner_id,
            NovelAnalysisVersion.project_id == job.project_id,
            NovelAnalysisVersion.status == "confirmed",
        ).order_by(NovelAnalysisVersion.id.desc()).first()
        brief = project.brief
        episode_payload = {
            "number": episode.number, "title": episode.title, "synopsis": episode.synopsis,
            "core_conflict": episode.core_conflict, "emotional_arc": episode.emotional_arc,
            "opening_hook": episode.opening_hook, "ending_hook": episode.ending_hook,
            "target_duration": episode.target_duration,
            "existing_scenes": screenplay_service._serialize_episodes([episode])[0].get("scenes", []),
        }
        if not progress(db, job, 20, f"AI 正在编写第 {episode.number} 集剧本"): return
        result, record = complete_json(db, job, "episode_screenplay", "episode_screenplay", {
            "brief": {"genre": brief.genre if brief else "", "audience": brief.audience if brief else "", "tone": brief.tone if brief else "", "target_duration": episode.target_duration},
            "analysis": analysis.content if analysis else {}, "episode": episode_payload,
            "instruction": job.input_payload.get("instruction") or "在保留现有分集目标的基础上生成完整场次剧本",
        })
        errors = _episode_candidate_errors(result)
        for scene_index, scene_payload in enumerate(result.get("scenes", [])):
            if not isinstance(scene_payload, dict):
                continue
            try:
                screenplay_service._validate_manual_scene(
                    db, job.owner_id, int(job.project_id), list(scene_payload.get("elements", [])),
                    list(scene_payload.get("source_references", [])), [], None,
                )
            except screenplay_service.ScreenplayValidationError as exc:
                errors.append({"path": f"scenes[{scene_index}].source_references", "message": str(exc)})
        candidate = ScreenplayRevisionCandidate(
            owner_id=job.owner_id, project_id=int(job.project_id), episode_id=episode.id,
            generation_record_id=record.id, base_lock_version=episode.lock_version,
            status="pending", instruction=str(job.input_payload.get("instruction") or ""),
            content=result, validation_errors=errors,
        )
        db.add(candidate); db.flush(); _finish_ai_job(db, job, {"candidate_id": candidate.id, "episode_id": episode.id, "validation_errors": errors}); return
    if job.job_type == "director_story_ledger":
        if not _director_ledger_available():
            raise AIResponseError("导演前期模块未启用")
        from app.short_drama.v3_director import ledger_service
        analysis = db.query(NovelAnalysisVersion).filter(
            NovelAnalysisVersion.id == int(job.input_payload["analysis_id"]),
            NovelAnalysisVersion.owner_id == job.owner_id,
            NovelAnalysisVersion.project_id == job.project_id,
        ).first()
        if not analysis:
            raise AIResponseError("小说分析版本不存在")
        if not progress(db, job, 20, "AI 正在构建故事台账和情感曲线"): return
        result, record = complete_json(db, job, "director_story_ledger", "director_story_ledger", {
            "analysis": analysis.content,
        })
        beats = result.get("beats")
        if not isinstance(beats, list) or not beats:
            raise AIResponseError("模型没有返回节拍数据")
        ledger, errors = ledger_service.create_ledger_from_beats(
            db,
            project_id=int(job.project_id),
            document_id=analysis.document_id,
            analysis_id=analysis.id,
            name=str(result.get("name") or f"故事台账 v{analysis.version}"),
            summary=str(result.get("summary") or ""),
            content={"source_analysis_version": analysis.version},
            beats=[b for b in beats if isinstance(b, dict)],
            generation_record_id=record.id,
            provenance={"ai_generated": True, "operation": "director_story_ledger"},
        )
        # 保存 Checkpoint A 决策（源材料矛盾）
        decisions_payload = []
        for item in result.get("decisions", []) or []:
            if not isinstance(item, dict) or not item.get("question"):
                continue
            d = ledger_service.add_decision(
                db,
                project_id=int(job.project_id),
                ledger_version_id=ledger.id,
                owner_id=job.owner_id,
                question=str(item.get("question")),
                options=[str(o) for o in (item.get("options") or []) if o],
            )
            decisions_payload.append(d.id)
        _finish_ai_job(db, job, {
            "ledger_id": ledger.id,
            "version": ledger.version,
            "beat_count": len(beats),
            "validation_errors": errors,
            "decision_ids": decisions_payload,
        })
        return
    raise AIResponseError(f"不支持的 AI 创作任务：{job.job_type}")
