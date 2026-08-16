"""AI provider configuration and OpenAI-compatible structured generation."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from datetime import UTC, datetime
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


class AIConfigurationError(ValueError): pass
class AIResponseError(ValueError): pass


PROMPTS = {
    "novel_chunk_analysis": (
        "小说分块分析", "你是专业短剧编剧分析师。只输出一个 JSON 对象，不使用 Markdown。不得虚构原文没有的信息。",
        "分析下面的小说原文，输出 synopsis、characters、locations、events、timeline、conflicts、hooks、facts、source_references。"
        "characters/locations/events 均为数组；source_references 使用 chapter_number、paragraph_start、paragraph_end。\n\n{content}",
    ),
    "novel_analysis_merge": (
        "小说分析合并", "你是故事编辑。只输出一个 JSON 对象，合并重复实体，保留来源引用，不得增加输入中没有的事实。",
        "合并以下分块分析，输出 synopsis、core_conflict、characters、locations、events、timeline、hooks、emotional_beats、facts、source_references。\n\n{content}",
    ),
    "novel_adaptation": (
        "小说改编方案", "你是短剧总编剧。只输出 JSON，严格保持可追溯性，不得改变故事核心事实。",
        "根据故事档案和创作简报生成改编候选。根对象为 options 数组。每个方案必须包含 key、label、description、metrics、episodes。"
        "每集包含 title、synopsis、target_duration、scenes；场景包含 heading、location_name、time_of_day、interior_exterior、content、elements、source_references、purpose、target_duration。"
        "elements 类型只能是 action/dialogue/narration/transition。只生成这些策略：{strategies}。目标 {episode_count} 集。\n\n故事档案：{analysis}\n\n创作简报：{brief}",
    ),
    "episode_screenplay": (
        "单集剧本生成", "你是短剧分集编剧。只输出一个 JSON 对象。保留已确定的人物事实和原文引用，不得虚构不存在的来源。",
        "为指定分集生成可拍摄的结构化剧本候选。根对象包含 title、synopsis、core_conflict、emotional_arc、opening_hook、ending_hook、target_duration、scenes。"
        "每个场景包含 heading、location_name、time_of_day、interior_exterior、content、elements、source_references、purpose、target_duration；"
        "elements 类型只能是 action/dialogue/narration/transition，对白可包含 speaker。总场景时长应接近单集目标时长。\n\n"
        "项目简报：{brief}\n故事档案：{analysis}\n当前分集：{episode}\n人工要求：{instruction}",
    ),
    "json_repair": (
        "JSON 修复", "你是 JSON 修复器。只输出修复后的 JSON，不解释，不改变语义。",
        "以下模型输出无法解析为 JSON，请修复：\n\n{content}",
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
        if not db.query(AIPromptTemplate.id).filter(AIPromptTemplate.code == code, AIPromptTemplate.version == 1).first():
            db.add(AIPromptTemplate(code=code, name=name, version=1, system_prompt=system_prompt, user_prompt=user_prompt, response_schema={}, enabled=True))
    db.commit()


def prompt_template(db: Session, code: str) -> AIPromptTemplate:
    item = db.query(AIPromptTemplate).filter(AIPromptTemplate.code == code, AIPromptTemplate.enabled.is_(True)).order_by(AIPromptTemplate.version.desc()).first()
    if not item: raise AIConfigurationError(f"AI 提示词模板不存在：{code}")
    return item


def _json_content(value: str) -> dict[str, Any]:
    text = value.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I); text = re.sub(r"\s*```$", "", text)
    try: data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start: raise AIResponseError("模型没有返回 JSON 对象")
        try: data = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc: raise AIResponseError(f"模型 JSON 解析失败：{exc.msg}") from exc
    if not isinstance(data, dict): raise AIResponseError("模型返回的 JSON 根节点必须是对象")
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
        record.response_snapshot={"content": parsed}; record.status="succeeded"; record.duration_ms=round((time.monotonic()-started)*1000); record.finished_at=_now(); db.commit(); db.refresh(record)
        return parsed, record
    except Exception as exc:
        record.status="failed"; record.error=str(exc)[:4000]; record.duration_ms=round((time.monotonic()-started)*1000); record.finished_at=_now(); db.commit()
        raise AIResponseError(str(exc)) from exc


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


def _episode_candidate_errors(content: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
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
    if candidate.status != "pending" or candidate.validation_errors:
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
    errors: list[dict[str, Any]] = []
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
        analysis=NovelAnalysisVersion(owner_id=job.owner_id,project_id=int(job.project_id),document_id=document.id,generation_record_id=last_record.id if last_record else None,version=version,status="invalid" if errors else "candidate",chapter_start=start,chapter_end=end,content=content,validation_errors=errors)
        db.add(analysis);db.flush();_finish_ai_job(db,job,{"analysis_id":analysis.id,"version":version,"validation_errors":errors});return
    if job.job_type == "generate_adaptation":
        analysis=db.query(NovelAnalysisVersion).filter(NovelAnalysisVersion.id==int(job.input_payload["analysis_id"]),NovelAnalysisVersion.owner_id==job.owner_id).first()
        if not analysis: raise AIResponseError("小说分析版本不存在")
        project=project_service.owned_project(db,job.owner_id,int(job.project_id));brief=project.brief
        count=int(job.input_payload.get("episode_count") or (brief.episode_count if brief else 1));strategies=job.input_payload.get("strategies") or ["faithful","high_tempo","emotional"]
        if not progress(db,job,20,"AI 正在设计改编策略和分集结构"): return
        result,_=complete_json(db,job,"novel_adaptation","novel_adaptation",{"analysis":analysis.content,"brief":{"genre":brief.genre if brief else "","audience":brief.audience if brief else "","tone":brief.tone if brief else "","platform":brief.platform if brief else "","episode_duration":brief.episode_duration if brief else 60,"visual_style":brief.visual_style if brief else ""},"strategies":",".join(strategies),"episode_count":count})
        options=result.get("options")
        if not isinstance(options,list) or not options: raise AIResponseError("模型没有返回改编方案")
        document=screenplay_service._owned_document(db,job.owner_id,int(job.project_id),analysis.document_id)
        errors=[{"option":option.get("key","unknown"),**error} for option in options if isinstance(option,dict) for error in screenplay_service._validate_option(option,document)]
        candidate=AdaptationCandidate(owner_id=job.owner_id,project_id=int(job.project_id),document_id=document.id,chapter_start=analysis.chapter_start,chapter_end=analysis.chapter_end,status="invalid" if errors else "pending",options=options,validation_errors=errors)
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
            status="invalid" if errors else "pending", instruction=str(job.input_payload.get("instruction") or ""),
            content=result, validation_errors=errors,
        )
        db.add(candidate); db.flush(); _finish_ai_job(db, job, {"candidate_id": candidate.id, "episode_id": episode.id, "validation_errors": errors}); return
    raise AIResponseError(f"不支持的 AI 创作任务：{job.job_type}")
