"""V2.1 AI 短剧模块入口。"""
from __future__ import annotations

from typing import Literal

from typing_extensions import TypedDict

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from app.config import settings
from app.core.deps import AdminUser, CurrentUser, DBSession
from app.models import AIProviderConfig, AdaptationCandidate, Character, CharacterRelationship, Location, NovelAnalysisVersion, Prop, ScreenplayRevisionCandidate, ShotTaskLink
from app.schemas.short_drama import (
    ProjectBriefOut,
    ProjectBriefPatchIn,
    ProjectCreateIn,
    ProjectListOut,
    ProjectOut,
    ProjectOverviewOut,
    ProjectPatchIn,
    CreativeJobListOut,
    CreativeJobOut,
    DocumentImportOut,
    SourceDocumentOut,
    AdaptationCandidateCreateIn,
    AdaptationCandidateOut,
    AdaptationConfirmIn,
    EpisodeCreateIn,
    EpisodeOut,
    EpisodePatchIn,
    SceneCreateIn,
    SceneOut,
    ScenePatchIn,
    ScreenplayOut,
    ScreenplayReorderIn,
    SourceChapterContentOut,
    SourceContentOut,
    SourceParagraphOut,
    StoryVersionCreateIn,
    StoryVersionListOut,
    StoryVersionOut,
    StoryVersionRenameIn,
    CharacterInput, CharacterOut, CharacterVariantInput, CharacterVariantOut, LocationInput, LocationOut, PropInput, PropOut,
    RelationshipInput, RelationshipOut, ResourceUsageOut, WorldCandidateConfirmIn,
    WorldCandidateOut, WorldOverviewOut,
    ShotBulkPatchIn, ShotInput, ShotMergeIn, ShotOut, ShotPatchIn, ShotReorderIn, ShotSplitIn,
    StoryboardCandidateConfirmIn, StoryboardCandidateCreateIn, StoryboardCandidateOut,
    StoryboardEpisodeOut, StoryboardOut, StoryboardSceneOut,
    CompiledShotTaskOut, ShotProductionCompileIn, ShotProductionCreateIn,
    ShotProductionCreateOut, ShotProductionOut, ShotTaskLinkOut, TakeOut,
    TakeRegenerateIn, TakeReviewIn,
    AIAdaptationIn, AIGenerationRecordOut, AIProviderInput, AIProviderOut, AIPromptTemplateOut, AIPromptTemplateUpdateIn, EpisodeAIGenerateIn, NovelAnalyzeIn, NovelAnalysisOut,
    ScreenplayRevisionCandidateOut,
    ProjectQuickCreateIn, ProjectQuickCreateOut, EpisodeScriptPatchIn, EpisodeScriptOut,
    ScriptManifestGenerateIn, ScriptManifestPatchIn, ScriptManifestSplitIn, ScriptManifestOut,
    PhaseOneCastingOut, ProjectAssetCopyOut, ProjectAssetVersionCreateIn, ProjectAssetVersionOut,
    ShotCharacterBindingIn, ShotCharacterBindingOut,
)
from app.short_drama import ai_service, document_service, phase1_service, production_service, project_service, screenplay_service, storyboard_service, world_service, v65_pipeline_service

router = APIRouter(prefix="/short-drama", tags=["v2-short-drama"])


class ShortDramaCapabilities(TypedDict):
    projects: bool
    story_import: bool
    story_bible: bool
    storyboard: bool
    task_bridge: bool
    screenplay: bool
    world_setting: bool
    ai_adaptation: bool


class ShortDramaStatus(TypedDict):
    enabled: bool
    version: Literal["2.1"]
    stage: Literal["production"]
    capabilities: ShortDramaCapabilities


@router.get("/status")
def module_status(user: CurrentUser) -> ShortDramaStatus:
    """返回当前部署的 V2.1 模块状态与已开放能力。

    即使功能关闭仍保留该探测接口，前端可据此显示安全的回退状态；
    后续业务接口必须在服务层再次校验 ``short_drama_enabled``。
    """

    return {
        "enabled": settings.short_drama_enabled,
        "version": "2.1",
        "stage": "production",
        "capabilities": {
            "projects": True,
            "story_import": True,
            "story_bible": False,
            "storyboard": True,
            "task_bridge": True,
            "screenplay": True,
            "world_setting": True,
            "ai_adaptation": True,
        },
    }


def _require_enabled() -> None:
    if not settings.short_drama_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "短剧模块当前未启用")


def _not_found_or_conflict(exc: Exception) -> HTTPException:
    if isinstance(exc, project_service.ProjectNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.get("/projects", response_model=ProjectListOut)
def list_projects(
    user: CurrentUser,
    db: DBSession,
    keyword: str | None = None,
    project_status: str | None = Query(default=None, alias="status"),
    include_deleted: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ProjectListOut:
    _require_enabled()
    items, total = project_service.list_projects(
        db,
        user.id,
        keyword=keyword,
        status=project_status,
        include_deleted=include_deleted,
        page=page,
        page_size=page_size,
    )
    return ProjectListOut(items=items, total=total, page=page, page_size=page_size)


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreateIn, user: CurrentUser, db: DBSession) -> ProjectOut:
    _require_enabled()
    return ProjectOut.model_validate(project_service.create_project(db, user.id, body))


@router.post("/projects/quick-create", response_model=ProjectQuickCreateOut, status_code=status.HTTP_201_CREATED)
def quick_create_project(body: ProjectQuickCreateIn, user: CurrentUser, db: DBSession) -> ProjectQuickCreateOut:
    _require_enabled()
    project, episode = phase1_service.quick_create(db, user.id, body)
    return ProjectQuickCreateOut(project=ProjectOut.model_validate(project), episode_id=episode.id)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, user: CurrentUser, db: DBSession) -> ProjectOut:
    _require_enabled()
    try:
        project = project_service.owned_project(db, user.id, project_id)
    except project_service.ProjectNotFoundError as exc:
        raise _not_found_or_conflict(exc)
    return ProjectOut.model_validate(project)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def patch_project(project_id: int, body: ProjectPatchIn, user: CurrentUser, db: DBSession) -> ProjectOut:
    _require_enabled()
    try:
        project = project_service.update_project(db, user.id, project_id, body)
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError) as exc:
        raise _not_found_or_conflict(exc)
    return ProjectOut.model_validate(project)


@router.delete("/projects/{project_id}", response_model=ProjectOut)
def delete_project(project_id: int, user: CurrentUser, db: DBSession) -> ProjectOut:
    _require_enabled()
    try:
        project = project_service.delete_project(db, user.id, project_id)
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError) as exc:
        raise _not_found_or_conflict(exc)
    return ProjectOut.model_validate(project)


@router.post("/projects/{project_id}/restore", response_model=ProjectOut)
def restore_project(project_id: int, user: CurrentUser, db: DBSession) -> ProjectOut:
    _require_enabled()
    try:
        project = project_service.restore_project(db, user.id, project_id)
    except project_service.ProjectNotFoundError as exc:
        raise _not_found_or_conflict(exc)
    return ProjectOut.model_validate(project)


@router.get("/projects/{project_id}/brief", response_model=ProjectBriefOut)
def get_brief(project_id: int, user: CurrentUser, db: DBSession) -> ProjectBriefOut:
    _require_enabled()
    try:
        project = project_service.owned_project(db, user.id, project_id)
        if not project.brief:
            raise project_service.ProjectNotFoundError("创作简报不存在")
    except project_service.ProjectNotFoundError as exc:
        raise _not_found_or_conflict(exc)
    return ProjectBriefOut.model_validate(project.brief)


@router.put("/projects/{project_id}/brief", response_model=ProjectBriefOut)
def put_brief(
    project_id: int,
    body: ProjectBriefPatchIn,
    user: CurrentUser,
    db: DBSession,
) -> ProjectBriefOut:
    _require_enabled()
    try:
        brief = project_service.update_brief(db, user.id, project_id, body)
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError) as exc:
        raise _not_found_or_conflict(exc)
    return ProjectBriefOut.model_validate(brief)


@router.get("/projects/{project_id}/overview", response_model=ProjectOverviewOut)
def overview(project_id: int, user: CurrentUser, db: DBSession) -> ProjectOverviewOut:
    _require_enabled()
    try:
        data = project_service.project_overview(db, user.id, project_id)
    except project_service.ProjectNotFoundError as exc:
        raise _not_found_or_conflict(exc)
    return ProjectOverviewOut.model_validate(data)


@router.get("/projects/{project_id}/episodes/{episode_id}/script", response_model=EpisodeScriptOut)
def get_episode_script(project_id: int, episode_id: int, user: CurrentUser, db: DBSession) -> EpisodeScriptOut:
    _require_enabled()
    try: return EpisodeScriptOut.model_validate(phase1_service.get_script(db, user.id, project_id, episode_id))
    except project_service.ProjectNotFoundError as exc: raise _not_found_or_conflict(exc)


@router.patch("/projects/{project_id}/episodes/{episode_id}/script", response_model=EpisodeScriptOut)
def patch_episode_script(project_id: int, episode_id: int, body: EpisodeScriptPatchIn, user: CurrentUser, db: DBSession) -> EpisodeScriptOut:
    _require_enabled()
    try:
        result = phase1_service.update_script(db, user.id, project_id, episode_id, lock_version=body.lock_version, mode=body.mode, text=body.text, settings=body.settings)
        return EpisodeScriptOut.model_validate(result)
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError) as exc: raise _not_found_or_conflict(exc)


@router.post("/projects/{project_id}/episodes/{episode_id}/manifests/generate", response_model=CreativeJobOut, status_code=status.HTTP_202_ACCEPTED)
def generate_script_manifest(project_id: int, episode_id: int, body: ScriptManifestGenerateIn, user: CurrentUser, db: DBSession) -> CreativeJobOut:
    """提交后台 AI 拍摄清单任务，避免长模型请求占用 HTTP 连接。"""
    _require_enabled()
    try:
        if body.provider_config_id:
            return CreativeJobOut.model_validate(ai_service.create_script_manifest_job(db, user.id, project_id, episode_id, provider_config_id=body.provider_config_id, idempotency_key=body.idempotency_key))
        # 未配置模型时仍保留本地规则降级，但用已完成作业统一前端契约。
        manifest = phase1_service.generate_manifest(db, user.id, project_id, episode_id)
        return CreativeJobOut.model_validate(ai_service.completed_local_job(db, user.id, project_id, episode_id, body.idempotency_key, manifest.id))
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError, ai_service.AIConfigurationError, ai_service.AIResponseError) as exc: raise _not_found_or_conflict(exc)


@router.get("/projects/{project_id}/episodes/{episode_id}/manifests", response_model=list[ScriptManifestOut])
def list_script_manifests(project_id: int, episode_id: int, user: CurrentUser, db: DBSession) -> list[ScriptManifestOut]:
    _require_enabled()
    try: return [ScriptManifestOut.model_validate(x) for x in phase1_service.list_manifests(db, user.id, project_id, episode_id)]
    except project_service.ProjectNotFoundError as exc: raise _not_found_or_conflict(exc)


@router.patch("/projects/{project_id}/episodes/{episode_id}/manifests/{manifest_id}", response_model=ScriptManifestOut)
def patch_script_manifest(project_id: int, episode_id: int, manifest_id: int, body: ScriptManifestPatchIn, user: CurrentUser, db: DBSession) -> ScriptManifestOut:
    _require_enabled()
    try: return ScriptManifestOut.model_validate(phase1_service.patch_manifest(db, user.id, project_id, episode_id, manifest_id, lock_version=body.lock_version, summary=body.summary, content=body.content))
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError) as exc: raise _not_found_or_conflict(exc)


@router.post("/projects/{project_id}/episodes/{episode_id}/manifests/{manifest_id}/confirm", response_model=ScriptManifestOut)
def confirm_script_manifest(project_id: int, episode_id: int, manifest_id: int, user: CurrentUser, db: DBSession) -> ScriptManifestOut:
    _require_enabled()
    try: return ScriptManifestOut.model_validate(phase1_service.confirm_manifest(db, user.id, project_id, episode_id, manifest_id))
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError) as exc: raise _not_found_or_conflict(exc)


@router.post("/projects/{project_id}/episodes/{episode_id}/manifests/{manifest_id}/unlock", response_model=ScriptManifestOut)
def unlock_script_manifest(project_id: int, episode_id: int, manifest_id: int, user: CurrentUser, db: DBSession) -> ScriptManifestOut:
    _require_enabled()
    try: return ScriptManifestOut.model_validate(phase1_service.unlock_manifest(db, user.id, project_id, episode_id, manifest_id))
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError) as exc: raise _not_found_or_conflict(exc)


@router.post("/projects/{project_id}/episodes/{episode_id}/manifests/{manifest_id}/review", response_model=ScriptManifestOut)
def review_script_manifest(project_id: int, episode_id: int, manifest_id: int, user: CurrentUser, db: DBSession) -> ScriptManifestOut:
    _require_enabled()
    try: return ScriptManifestOut.model_validate(phase1_service.review_manifest(db, user.id, project_id, episode_id, manifest_id))
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError) as exc: raise _not_found_or_conflict(exc)


@router.delete("/projects/{project_id}/episodes/{episode_id}/manifests/{manifest_id}")
def delete_script_manifest(project_id: int, episode_id: int, manifest_id: int, user: CurrentUser, db: DBSession) -> dict[str, bool]:
    _require_enabled()
    try:
        phase1_service.delete_manifest(db, user.id, project_id, episode_id, manifest_id)
        return {"deleted": True}
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError) as exc: raise _not_found_or_conflict(exc)


@router.get("/projects/{project_id}/episodes/{episode_id}/pipeline")
def get_v65_pipeline(project_id: int, episode_id: int, user: CurrentUser, db: DBSession) -> dict:
    _require_enabled()
    try:
        return v65_pipeline_service.snapshot(db, user.id, project_id, episode_id)
    except project_service.ProjectNotFoundError as exc:
        raise _not_found_or_conflict(exc)


@router.post("/projects/{project_id}/episodes/{episode_id}/asset-atlas/confirm")
def confirm_v65_asset_atlas(project_id: int, episode_id: int, user: CurrentUser, db: DBSession) -> dict:
    _require_enabled()
    try:
        return v65_pipeline_service.confirm_asset_atlas(db, user.id, project_id, episode_id)
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError) as exc:
        raise _not_found_or_conflict(exc)


@router.post("/projects/{project_id}/episodes/{episode_id}/spatial-storyboard/confirm")
def confirm_v65_spatial_storyboard(project_id: int, episode_id: int, user: CurrentUser, db: DBSession) -> dict:
    _require_enabled()
    try:
        return v65_pipeline_service.confirm_spatial_storyboard(db, user.id, project_id, episode_id)
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError) as exc:
        raise _not_found_or_conflict(exc)


@router.post("/projects/{project_id}/episodes/{episode_id}/video-prompts/generate", response_model=CreativeJobOut, status_code=status.HTTP_202_ACCEPTED)
def generate_v65_video_prompts(project_id: int, episode_id: int, body: dict, user: CurrentUser, db: DBSession) -> CreativeJobOut:
    _require_enabled()
    try:
        v65_pipeline_service.require_video_prompt_gate(db, user.id, project_id, episode_id)
        return CreativeJobOut.model_validate(ai_service.create_video_prompt_job(
            db, user.id, project_id, episode_id, int(body.get("manifest_id") or 0),
            provider_config_id=body.get("provider_config_id"), idempotency_key=str(body.get("idempotency_key") or ""),
            model_adapter=str(body.get("model_adapter") or "seedance_2_5")))
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError, ai_service.AIConfigurationError, ai_service.AIResponseError) as exc:
        raise _not_found_or_conflict(exc)


@router.get("/projects/{project_id}/casting", response_model=PhaseOneCastingOut)
def phase_one_casting(project_id: int, user: CurrentUser, db: DBSession) -> PhaseOneCastingOut:
    _require_enabled()
    try: return PhaseOneCastingOut.model_validate(phase1_service.casting(db, user.id, project_id))
    except project_service.ProjectNotFoundError as exc: raise _not_found_or_conflict(exc)


@router.post("/projects/{project_id}/assets/{entity_type}/{entity_id}/copy", response_model=ProjectAssetCopyOut, status_code=status.HTTP_201_CREATED)
def copy_project_asset(project_id: int, entity_type: str, entity_id: int, user: CurrentUser, db: DBSession) -> ProjectAssetCopyOut:
    _require_enabled()
    try: return ProjectAssetCopyOut.model_validate(phase1_service.copy_asset(db, user.id, project_id, entity_type, entity_id))
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError) as exc: raise _not_found_or_conflict(exc)


@router.post("/projects/{project_id}/assets/{entity_type}/{entity_id}/versions", response_model=ProjectAssetVersionOut, status_code=status.HTTP_201_CREATED)
def create_project_asset_version(project_id: int, entity_type: str, entity_id: int, body: ProjectAssetVersionCreateIn, user: CurrentUser, db: DBSession) -> ProjectAssetVersionOut:
    _require_enabled()
    try: return ProjectAssetVersionOut.model_validate(phase1_service.create_asset_version(db, user.id, project_id, entity_type, entity_id, **body.model_dump()))
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError) as exc: raise _not_found_or_conflict(exc)


@router.post("/projects/{project_id}/asset-versions/{version_id}/adopt", response_model=ProjectAssetVersionOut)
def adopt_project_asset_version(project_id: int, version_id: int, user: CurrentUser, db: DBSession) -> ProjectAssetVersionOut:
    _require_enabled()
    try: return ProjectAssetVersionOut.model_validate(phase1_service.adopt_asset_version(db, user.id, project_id, version_id))
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError) as exc: raise _not_found_or_conflict(exc)


@router.put("/projects/{project_id}/shots/{shot_id}/character-binding", response_model=ShotCharacterBindingOut)
def bind_shot_character(project_id: int, shot_id: int, body: ShotCharacterBindingIn, user: CurrentUser, db: DBSession) -> ShotCharacterBindingOut:
    _require_enabled()
    try: return ShotCharacterBindingOut.model_validate(phase1_service.bind_character(db, user.id, project_id, shot_id, body.character_id, body.variant_id))
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError) as exc: raise _not_found_or_conflict(exc)


@router.post(
    "/projects/{project_id}/imports",
    response_model=DocumentImportOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def import_document(
    project_id: int,
    user: CurrentUser,
    db: DBSession,
    file: UploadFile = File(...),
) -> DocumentImportOut:
    _require_enabled()
    try:
        document, job = await document_service.create_import(db, user.id, project_id, file)
    except project_service.ProjectNotFoundError as exc:
        raise _not_found_or_conflict(exc)
    except (document_service.DocumentImportError, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return DocumentImportOut(
        document=SourceDocumentOut.model_validate(document),
        job=CreativeJobOut.model_validate(job),
    )


@router.get("/projects/{project_id}/documents", response_model=list[SourceDocumentOut])
def list_project_documents(project_id: int, user: CurrentUser, db: DBSession) -> list[SourceDocumentOut]:
    _require_enabled()
    try:
        documents = document_service.list_documents(db, user.id, project_id)
    except project_service.ProjectNotFoundError as exc:
        raise _not_found_or_conflict(exc)
    return [SourceDocumentOut.model_validate(item) for item in documents]


@router.get("/jobs", response_model=CreativeJobListOut)
def list_creative_jobs(
    user: CurrentUser,
    db: DBSession,
    project_id: int | None = None,
    job_status: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> CreativeJobListOut:
    _require_enabled()
    try:
        items, total = document_service.list_jobs(
            db, user.id, project_id=project_id, status=job_status, page=page, page_size=page_size
        )
    except project_service.ProjectNotFoundError as exc:
        raise _not_found_or_conflict(exc)
    return CreativeJobListOut(items=items, total=total, page=page, page_size=page_size)


@router.get("/jobs/{job_id}", response_model=CreativeJobOut)
def get_creative_job(job_id: int, user: CurrentUser, db: DBSession) -> CreativeJobOut:
    _require_enabled()
    try:
        job = document_service.owned_job(db, user.id, job_id)
    except project_service.ProjectNotFoundError as exc:
        raise _not_found_or_conflict(exc)
    return CreativeJobOut.model_validate(job)


@router.post("/jobs/{job_id}/cancel", response_model=CreativeJobOut)
def cancel_creative_job(job_id: int, user: CurrentUser, db: DBSession) -> CreativeJobOut:
    _require_enabled()
    try:
        job = document_service.cancel_job(db, user.id, job_id)
    except project_service.ProjectNotFoundError as exc:
        raise _not_found_or_conflict(exc)
    except document_service.DocumentImportError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return CreativeJobOut.model_validate(job)


@router.post("/jobs/{job_id}/retry", response_model=CreativeJobOut)
def retry_creative_job(job_id: int, user: CurrentUser, db: DBSession) -> CreativeJobOut:
    _require_enabled()
    try:
        job = document_service.retry_job(db, user.id, job_id)
    except project_service.ProjectNotFoundError as exc:
        raise _not_found_or_conflict(exc)
    except document_service.DocumentImportError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return CreativeJobOut.model_validate(job)


@router.get("/ai/providers", response_model=list[AIProviderOut])
def list_ai_providers(user: CurrentUser, db: DBSession) -> list[AIProviderOut]:
    _require_enabled()
    query = db.query(AIProviderConfig)
    if user.role != "admin": query = query.filter(AIProviderConfig.enabled.is_(True))
    return [AIProviderOut.model_validate(item) for item in query.order_by(AIProviderConfig.is_default.desc(), AIProviderConfig.id).all()]


@router.post("/ai/providers", response_model=AIProviderOut, status_code=status.HTTP_201_CREATED)
def create_ai_provider(body: AIProviderInput, admin: AdminUser, db: DBSession) -> AIProviderOut:
    _require_enabled()
    try: return AIProviderOut.model_validate(ai_service.save_provider(db, admin.id, body))
    except (ai_service.AIConfigurationError, ValueError) as exc: raise _screenplay_error(exc)


@router.put("/ai/providers/{provider_id}", response_model=AIProviderOut)
def update_ai_provider(provider_id: int, body: AIProviderInput, admin: AdminUser, db: DBSession) -> AIProviderOut:
    _require_enabled()
    try: return AIProviderOut.model_validate(ai_service.save_provider(db, admin.id, body, provider_id))
    except (project_service.ProjectNotFoundError, ai_service.AIConfigurationError, ValueError) as exc: raise _screenplay_error(exc)


@router.delete("/ai/providers/{provider_id}")
def delete_ai_provider(provider_id: int, admin: AdminUser, db: DBSession) -> dict[str, bool]:
    _require_enabled()
    try: ai_service.delete_provider(db, provider_id)
    except project_service.ProjectNotFoundError as exc: raise _screenplay_error(exc)
    return {"deleted": True}


@router.post("/ai/providers/{provider_id}/test")
def test_ai_provider(provider_id: int, admin: AdminUser, db: DBSession) -> dict:
    _require_enabled()
    try: return ai_service.test_provider(db, provider_id)
    except Exception as exc: raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"连接测试失败：{exc}")


# ---- AI 提示词模板管理 ----

@router.get("/ai/prompt-templates", response_model=list[AIPromptTemplateOut])
def list_prompt_templates(db: DBSession, code: str | None = None) -> list[AIPromptTemplateOut]:
    _require_enabled()
    from app.models import AIPromptTemplate
    q = db.query(AIPromptTemplate).filter(AIPromptTemplate.enabled.is_(True))
    if code:
        q = q.filter(AIPromptTemplate.code == code)
    items = q.order_by(AIPromptTemplate.code, AIPromptTemplate.version.desc()).all()
    # 每个 code 只返回最新版本
    seen: set[str] = set()
    result: list[AIPromptTemplateOut] = []
    for item in items:
        if item.code in seen:
            continue
        seen.add(item.code)
        result.append(AIPromptTemplateOut.model_validate(item))
    return result


@router.put("/ai/prompt-templates/{template_id}", response_model=AIPromptTemplateOut)
def update_prompt_template(template_id: int, body: AIPromptTemplateUpdateIn, admin: AdminUser, db: DBSession) -> AIPromptTemplateOut:
    _require_enabled()
    from app.models import AIPromptTemplate
    item = db.get(AIPromptTemplate, template_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "提示词模板不存在")
    # 不修改原始 v1 种子模板，而是创建新版本
    latest = (
        db.query(AIPromptTemplate)
        .filter(AIPromptTemplate.code == item.code)
        .order_by(AIPromptTemplate.version.desc())
        .first()
    )
    new_version = (latest.version + 1) if latest else item.version + 1
    # 旧版本禁用
    db.query(AIPromptTemplate).filter(
        AIPromptTemplate.code == item.code, AIPromptTemplate.enabled.is_(True)
    ).update({AIPromptTemplate.enabled: False}, synchronize_session=False)
    new_item = AIPromptTemplate(
        code=item.code, name=item.name, version=new_version,
        system_prompt=body.system_prompt, user_prompt=body.user_prompt,
        response_schema=item.response_schema, enabled=True, created_by=admin.id,
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return AIPromptTemplateOut.model_validate(new_item)


@router.get("/projects/{project_id}/ai/records", response_model=list[AIGenerationRecordOut])
def list_ai_records(
    project_id: int,
    user: CurrentUser,
    db: DBSession,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
    operation: str | None = Query(default=None),
    job_id: int | None = Query(default=None),
) -> list[AIGenerationRecordOut]:
    """列出项目的 AI 调用日志（按时间倒序），可按状态/操作/任务过滤。"""
    _require_enabled()
    try:
        project_service.owned_project(db, user.id, project_id)
    except project_service.ProjectNotFoundError as exc:
        raise _screenplay_error(exc)
    from app.models import AIGenerationRecord
    query = db.query(AIGenerationRecord).filter(AIGenerationRecord.project_id == project_id)
    if status_filter:
        query = query.filter(AIGenerationRecord.status == status_filter)
    if operation:
        query = query.filter(AIGenerationRecord.operation == operation)
    if job_id is not None:
        query = query.filter(AIGenerationRecord.job_id == job_id)
    items = query.order_by(AIGenerationRecord.id.desc()).offset(offset).limit(limit).all()
    return [AIGenerationRecordOut.model_validate(item) for item in items]


@router.post("/projects/{project_id}/ai/analyze", response_model=CreativeJobOut, status_code=status.HTTP_202_ACCEPTED)
def analyze_novel(project_id: int, body: NovelAnalyzeIn, user: CurrentUser, db: DBSession) -> CreativeJobOut:
    _require_enabled()
    try: return CreativeJobOut.model_validate(ai_service.create_analysis_job(db, user.id, project_id, body))
    except (project_service.ProjectNotFoundError, screenplay_service.ScreenplayValidationError, ai_service.AIConfigurationError) as exc: raise _screenplay_error(exc)


@router.get("/projects/{project_id}/ai/analyses", response_model=list[NovelAnalysisOut])
def list_novel_analyses(project_id: int, user: CurrentUser, db: DBSession) -> list[NovelAnalysisOut]:
    _require_enabled()
    try: project_service.owned_project(db, user.id, project_id)
    except project_service.ProjectNotFoundError as exc: raise _screenplay_error(exc)
    items=db.query(NovelAnalysisVersion).filter(NovelAnalysisVersion.owner_id==user.id,NovelAnalysisVersion.project_id==project_id).order_by(NovelAnalysisVersion.id.desc()).all()
    return [NovelAnalysisOut.model_validate(item) for item in items]


@router.post("/projects/{project_id}/ai/analyses/{analysis_id}/confirm", response_model=NovelAnalysisOut)
def confirm_novel_analysis(project_id: int, analysis_id: int, user: CurrentUser, db: DBSession) -> NovelAnalysisOut:
    _require_enabled()
    try: project_service.owned_project(db,user.id,project_id)
    except project_service.ProjectNotFoundError as exc: raise _screenplay_error(exc)
    item=db.query(NovelAnalysisVersion).filter(NovelAnalysisVersion.id==analysis_id,NovelAnalysisVersion.owner_id==user.id,NovelAnalysisVersion.project_id==project_id).first()
    if not item: raise HTTPException(status.HTTP_404_NOT_FOUND,"小说分析版本不存在")
    db.query(NovelAnalysisVersion).filter(NovelAnalysisVersion.project_id==project_id,NovelAnalysisVersion.status=="confirmed").update({NovelAnalysisVersion.status:"candidate",NovelAnalysisVersion.confirmed_at:None},synchronize_session=False)
    item.status="confirmed";item.confirmed_at=ai_service._now();db.commit();db.refresh(item);return NovelAnalysisOut.model_validate(item)


@router.post("/projects/{project_id}/ai/adaptation", response_model=CreativeJobOut, status_code=status.HTTP_202_ACCEPTED)
def generate_ai_adaptation(project_id: int, body: AIAdaptationIn, user: CurrentUser, db: DBSession) -> CreativeJobOut:
    _require_enabled()
    try:return CreativeJobOut.model_validate(ai_service.create_adaptation_job(db,user.id,project_id,body))
    except (project_service.ProjectNotFoundError,ai_service.AIConfigurationError) as exc:raise _screenplay_error(exc)


def _screenplay_error(exc: Exception) -> HTTPException:
    if isinstance(exc, project_service.ProjectNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, project_service.ProjectConflictError):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


@router.get("/projects/{project_id}/documents/{document_id}/content", response_model=SourceContentOut)
def get_source_content(
    project_id: int, document_id: int, user: CurrentUser, db: DBSession,
    chapter_start: int | None = Query(default=None, ge=1), chapter_end: int | None = Query(default=None, ge=1),
) -> SourceContentOut:
    _require_enabled()
    try:
        document, chapters = screenplay_service.source_content(db, user.id, project_id, document_id, chapter_start, chapter_end)
    except (project_service.ProjectNotFoundError, screenplay_service.ScreenplayValidationError) as exc:
        raise _screenplay_error(exc)
    return SourceContentOut(
        document=SourceDocumentOut.model_validate(document),
        chapters=[SourceChapterContentOut(
            id=item.id, number=item.number, title=item.title, char_count=item.char_count,
            paragraphs=[SourceParagraphOut.model_validate(paragraph) for paragraph in item.paragraphs],
        ) for item in chapters],
    )


@router.post("/projects/{project_id}/adaptation-candidates", response_model=AdaptationCandidateOut, status_code=status.HTTP_201_CREATED)
def create_adaptation_candidate(
    project_id: int, body: AdaptationCandidateCreateIn, user: CurrentUser, db: DBSession,
) -> AdaptationCandidateOut:
    _require_enabled()
    try:
        candidate = screenplay_service.create_candidate(
            db, user.id, project_id, body.document_id, body.chapter_start, body.chapter_end, body.episode_count
        )
    except (project_service.ProjectNotFoundError, screenplay_service.ScreenplayValidationError) as exc:
        raise _screenplay_error(exc)
    return AdaptationCandidateOut.model_validate(candidate)


@router.get("/projects/{project_id}/adaptation-candidates", response_model=list[AdaptationCandidateOut])
def list_adaptation_candidates(project_id: int, user: CurrentUser, db: DBSession) -> list[AdaptationCandidateOut]:
    _require_enabled(); project_service.owned_project(db, user.id, project_id)
    items = db.query(AdaptationCandidate).filter(
        AdaptationCandidate.owner_id == user.id,
        AdaptationCandidate.project_id == project_id,
    ).order_by(AdaptationCandidate.id.desc()).all()
    return [AdaptationCandidateOut.model_validate(item) for item in items]


@router.post("/projects/{project_id}/adaptation-candidates/{candidate_id}/confirm", response_model=StoryVersionOut)
def confirm_adaptation_candidate(
    project_id: int, candidate_id: int, body: AdaptationConfirmIn, user: CurrentUser, db: DBSession,
) -> StoryVersionOut:
    _require_enabled()
    try:
        version = screenplay_service.confirm_candidate(db, user.id, project_id, candidate_id, body.option_key, body.version_name)
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError, screenplay_service.ScreenplayValidationError) as exc:
        raise _screenplay_error(exc)
    return StoryVersionOut.model_validate(version)


@router.get("/projects/{project_id}/screenplay", response_model=ScreenplayOut)
def get_screenplay(project_id: int, user: CurrentUser, db: DBSession) -> ScreenplayOut:
    _require_enabled()
    try: project, episodes, current, changed = screenplay_service.screenplay(db, user.id, project_id)
    except project_service.ProjectNotFoundError as exc: raise _screenplay_error(exc)
    return ScreenplayOut(project=ProjectOut.model_validate(project), episodes=episodes, current_version_id=current.id if current else None, draft_changed=changed)


@router.post("/projects/{project_id}/episodes", response_model=EpisodeOut, status_code=status.HTTP_201_CREATED)
def create_episode(project_id: int, body: EpisodeCreateIn, user: CurrentUser, db: DBSession) -> EpisodeOut:
    _require_enabled()
    try: item = screenplay_service.create_episode(db, user.id, project_id, body)
    except (project_service.ProjectNotFoundError, screenplay_service.ScreenplayValidationError) as exc: raise _screenplay_error(exc)
    return EpisodeOut.model_validate(item)


@router.patch("/projects/{project_id}/episodes/{episode_id}", response_model=EpisodeOut)
def patch_episode(project_id: int, episode_id: int, body: EpisodePatchIn, user: CurrentUser, db: DBSession) -> EpisodeOut:
    _require_enabled()
    try: item = screenplay_service.update_episode(db, user.id, project_id, episode_id, body)
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError) as exc: raise _screenplay_error(exc)
    return EpisodeOut.model_validate(item)


@router.post("/projects/{project_id}/episodes/{episode_id}/ai/generate", response_model=CreativeJobOut, status_code=status.HTTP_202_ACCEPTED)
def generate_episode_screenplay(project_id: int, episode_id: int, body: EpisodeAIGenerateIn, user: CurrentUser, db: DBSession) -> CreativeJobOut:
    _require_enabled()
    try:
        return CreativeJobOut.model_validate(ai_service.create_episode_screenplay_job(db, user.id, project_id, episode_id, body))
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError, ai_service.AIConfigurationError) as exc:
        raise _screenplay_error(exc)


@router.get("/projects/{project_id}/episodes/{episode_id}/ai/candidates", response_model=list[ScreenplayRevisionCandidateOut])
def list_episode_screenplay_candidates(project_id: int, episode_id: int, user: CurrentUser, db: DBSession) -> list[ScreenplayRevisionCandidateOut]:
    _require_enabled()
    try:
        items = ai_service.list_episode_candidates(db, user.id, project_id, episode_id)
    except project_service.ProjectNotFoundError as exc:
        raise _screenplay_error(exc)
    return [ScreenplayRevisionCandidateOut.model_validate(item) for item in items]


@router.post("/projects/{project_id}/episodes/{episode_id}/ai/candidates/{candidate_id}/confirm", response_model=StoryVersionOut)
def confirm_episode_screenplay_candidate(project_id: int, episode_id: int, candidate_id: int, user: CurrentUser, db: DBSession) -> StoryVersionOut:
    _require_enabled()
    try:
        version = ai_service.confirm_episode_candidate(db, user.id, project_id, episode_id, candidate_id)
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError, ai_service.AIConfigurationError) as exc:
        raise _screenplay_error(exc)
    return StoryVersionOut.model_validate(version)


@router.delete("/projects/{project_id}/episodes/{episode_id}")
def delete_episode(project_id: int, episode_id: int, user: CurrentUser, db: DBSession) -> dict[str, bool]:
    _require_enabled()
    try: screenplay_service.delete_episode(db, user.id, project_id, episode_id)
    except project_service.ProjectNotFoundError as exc: raise _screenplay_error(exc)
    return {"deleted": True}


@router.post("/projects/{project_id}/episodes/{episode_id}/scenes", response_model=SceneOut, status_code=status.HTTP_201_CREATED)
def create_scene(project_id: int, episode_id: int, body: SceneCreateIn, user: CurrentUser, db: DBSession) -> SceneOut:
    _require_enabled()
    try: item = screenplay_service.create_scene(db, user.id, project_id, episode_id, body)
    except (project_service.ProjectNotFoundError, screenplay_service.ScreenplayValidationError) as exc: raise _screenplay_error(exc)
    return SceneOut.model_validate(item)


@router.patch("/projects/{project_id}/scenes/{scene_id}", response_model=SceneOut)
def patch_scene(project_id: int, scene_id: int, body: ScenePatchIn, user: CurrentUser, db: DBSession) -> SceneOut:
    _require_enabled()
    try: item = screenplay_service.update_scene(db, user.id, project_id, scene_id, body)
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError, screenplay_service.ScreenplayValidationError) as exc: raise _screenplay_error(exc)
    return SceneOut.model_validate(item)


@router.delete("/projects/{project_id}/scenes/{scene_id}")
def delete_scene(project_id: int, scene_id: int, user: CurrentUser, db: DBSession) -> dict[str, bool]:
    _require_enabled()
    try: screenplay_service.delete_scene(db, user.id, project_id, scene_id)
    except project_service.ProjectNotFoundError as exc: raise _screenplay_error(exc)
    return {"deleted": True}


@router.put("/projects/{project_id}/screenplay/reorder", response_model=ScreenplayOut)
def reorder_screenplay(project_id: int, body: ScreenplayReorderIn, user: CurrentUser, db: DBSession) -> ScreenplayOut:
    _require_enabled()
    try:
        screenplay_service.reorder(db, user.id, project_id, body.episode_ids, body.scene_ids_by_episode)
        project, episodes, current, changed = screenplay_service.screenplay(db, user.id, project_id)
    except (project_service.ProjectNotFoundError, screenplay_service.ScreenplayValidationError) as exc: raise _screenplay_error(exc)
    return ScreenplayOut(project=ProjectOut.model_validate(project), episodes=episodes, current_version_id=current.id if current else None, draft_changed=changed)


@router.post("/projects/{project_id}/versions", response_model=StoryVersionOut, status_code=status.HTTP_201_CREATED)
def create_story_version(project_id: int, body: StoryVersionCreateIn, user: CurrentUser, db: DBSession) -> StoryVersionOut:
    _require_enabled()
    try: item = screenplay_service.create_manual_version(db, user.id, project_id, body.name)
    except (project_service.ProjectNotFoundError, screenplay_service.ScreenplayValidationError) as exc: raise _screenplay_error(exc)
    return StoryVersionOut.model_validate(item)


@router.get("/projects/{project_id}/versions", response_model=StoryVersionListOut)
def list_story_versions(project_id: int, user: CurrentUser, db: DBSession) -> StoryVersionListOut:
    _require_enabled()
    try: items = screenplay_service.list_versions(db, user.id, project_id)
    except project_service.ProjectNotFoundError as exc: raise _screenplay_error(exc)
    return StoryVersionListOut(items=items)


@router.get("/projects/{project_id}/versions/{version_id}", response_model=StoryVersionOut)
def get_story_version(project_id: int, version_id: int, user: CurrentUser, db: DBSession) -> StoryVersionOut:
    _require_enabled()
    try: item = screenplay_service.owned_version(db, user.id, project_id, version_id)
    except project_service.ProjectNotFoundError as exc: raise _screenplay_error(exc)
    return StoryVersionOut.model_validate(item)


@router.patch("/projects/{project_id}/versions/{version_id}", response_model=StoryVersionOut)
def rename_story_version(project_id: int, version_id: int, body: StoryVersionRenameIn, user: CurrentUser, db: DBSession) -> StoryVersionOut:
    _require_enabled()
    try: item = screenplay_service.rename_version(db, user.id, project_id, version_id, body.name)
    except project_service.ProjectNotFoundError as exc: raise _screenplay_error(exc)
    return StoryVersionOut.model_validate(item)


@router.post("/projects/{project_id}/versions/{version_id}/restore", response_model=StoryVersionOut)
def restore_story_version(project_id: int, version_id: int, user: CurrentUser, db: DBSession) -> StoryVersionOut:
    _require_enabled()
    try: item = screenplay_service.restore_version(db, user.id, project_id, version_id)
    except (project_service.ProjectNotFoundError, screenplay_service.ScreenplayValidationError) as exc: raise _screenplay_error(exc)
    return StoryVersionOut.model_validate(item)


@router.post("/projects/{project_id}/world-candidates", response_model=WorldCandidateOut, status_code=status.HTTP_201_CREATED)
def extract_world_candidate(project_id: int, user: CurrentUser, db: DBSession) -> WorldCandidateOut:
    _require_enabled()
    try: item = world_service.extract_candidate(db, user.id, project_id)
    except (project_service.ProjectNotFoundError, world_service.WorldValidationError) as exc: raise _screenplay_error(exc)
    return WorldCandidateOut.model_validate(item)


@router.post("/projects/{project_id}/world-candidates/{candidate_id}/confirm", response_model=WorldCandidateOut)
def confirm_world_candidate(project_id: int, candidate_id: int, body: WorldCandidateConfirmIn, user: CurrentUser, db: DBSession) -> WorldCandidateOut:
    _require_enabled()
    try: item = world_service.confirm_candidate(db, user.id, project_id, candidate_id, body.skip_existing)
    except (project_service.ProjectNotFoundError, world_service.WorldValidationError) as exc: raise _screenplay_error(exc)
    return WorldCandidateOut.model_validate(item)


@router.get("/projects/{project_id}/world", response_model=WorldOverviewOut)
def get_world(project_id: int, user: CurrentUser, db: DBSession) -> WorldOverviewOut:
    _require_enabled()
    try: characters, locations, props, relationships = world_service.overview(db, user.id, project_id)
    except project_service.ProjectNotFoundError as exc: raise _screenplay_error(exc)
    return WorldOverviewOut(characters=characters, locations=locations, props=props, relationships=relationships)


@router.post("/projects/{project_id}/characters", response_model=CharacterOut, status_code=status.HTTP_201_CREATED)
def create_character(project_id: int, body: CharacterInput, user: CurrentUser, db: DBSession) -> CharacterOut:
    _require_enabled()
    try: return CharacterOut.model_validate(world_service.save_character(db, user.id, project_id, body))
    except (project_service.ProjectNotFoundError, world_service.WorldValidationError) as exc: raise _screenplay_error(exc)


@router.put("/projects/{project_id}/characters/{item_id}", response_model=CharacterOut)
def update_character(project_id: int, item_id: int, body: CharacterInput, user: CurrentUser, db: DBSession) -> CharacterOut:
    _require_enabled()
    try: return CharacterOut.model_validate(world_service.save_character(db, user.id, project_id, body, item_id))
    except (project_service.ProjectNotFoundError, world_service.WorldValidationError) as exc: raise _screenplay_error(exc)


@router.delete("/projects/{project_id}/characters/{item_id}")
def delete_character(project_id: int, item_id: int, user: CurrentUser, db: DBSession) -> dict[str, bool]:
    _require_enabled()
    try: world_service.delete_item(db, Character, user.id, project_id, item_id); return {"deleted": True}
    except (project_service.ProjectNotFoundError, world_service.WorldValidationError) as exc: raise _screenplay_error(exc)


@router.post("/projects/{project_id}/characters/{character_id}/variants", response_model=CharacterVariantOut, status_code=status.HTTP_201_CREATED)
def create_character_variant(project_id: int, character_id: int, body: CharacterVariantInput, user: CurrentUser, db: DBSession) -> CharacterVariantOut:
    _require_enabled()
    try: return CharacterVariantOut.model_validate(world_service.save_character_variant(db, user.id, project_id, character_id, body))
    except (project_service.ProjectNotFoundError, world_service.WorldValidationError) as exc: raise _screenplay_error(exc)


@router.put("/projects/{project_id}/characters/{character_id}/variants/{item_id}", response_model=CharacterVariantOut)
def update_character_variant(project_id: int, character_id: int, item_id: int, body: CharacterVariantInput, user: CurrentUser, db: DBSession) -> CharacterVariantOut:
    _require_enabled()
    try: return CharacterVariantOut.model_validate(world_service.save_character_variant(db, user.id, project_id, character_id, body, item_id))
    except (project_service.ProjectNotFoundError, world_service.WorldValidationError) as exc: raise _screenplay_error(exc)


@router.delete("/projects/{project_id}/characters/{character_id}/variants/{item_id}")
def delete_character_variant(project_id: int, character_id: int, item_id: int, user: CurrentUser, db: DBSession) -> dict[str, bool]:
    _require_enabled()
    try: world_service.delete_character_variant(db, user.id, project_id, character_id, item_id); return {"deleted": True}
    except (project_service.ProjectNotFoundError, world_service.WorldValidationError) as exc: raise _screenplay_error(exc)


@router.post("/projects/{project_id}/locations", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
def create_location(project_id: int, body: LocationInput, user: CurrentUser, db: DBSession) -> LocationOut:
    _require_enabled()
    try: return LocationOut.model_validate(world_service.save_location(db, user.id, project_id, body))
    except (project_service.ProjectNotFoundError, world_service.WorldValidationError) as exc: raise _screenplay_error(exc)


@router.put("/projects/{project_id}/locations/{item_id}", response_model=LocationOut)
def update_location(project_id: int, item_id: int, body: LocationInput, user: CurrentUser, db: DBSession) -> LocationOut:
    _require_enabled()
    try: return LocationOut.model_validate(world_service.save_location(db, user.id, project_id, body, item_id))
    except (project_service.ProjectNotFoundError, world_service.WorldValidationError) as exc: raise _screenplay_error(exc)


@router.delete("/projects/{project_id}/locations/{item_id}")
def delete_location(project_id: int, item_id: int, user: CurrentUser, db: DBSession) -> dict[str, bool]:
    _require_enabled()
    try: world_service.delete_item(db, Location, user.id, project_id, item_id); return {"deleted": True}
    except (project_service.ProjectNotFoundError, world_service.WorldValidationError) as exc: raise _screenplay_error(exc)


@router.post("/projects/{project_id}/props", response_model=PropOut, status_code=status.HTTP_201_CREATED)
def create_prop(project_id: int, body: PropInput, user: CurrentUser, db: DBSession) -> PropOut:
    _require_enabled()
    try: return PropOut.model_validate(world_service.save_prop(db, user.id, project_id, body))
    except (project_service.ProjectNotFoundError, world_service.WorldValidationError) as exc: raise _screenplay_error(exc)


@router.put("/projects/{project_id}/props/{item_id}", response_model=PropOut)
def update_prop(project_id: int, item_id: int, body: PropInput, user: CurrentUser, db: DBSession) -> PropOut:
    _require_enabled()
    try: return PropOut.model_validate(world_service.save_prop(db, user.id, project_id, body, item_id))
    except (project_service.ProjectNotFoundError, world_service.WorldValidationError) as exc: raise _screenplay_error(exc)


@router.delete("/projects/{project_id}/props/{item_id}")
def delete_prop(project_id: int, item_id: int, user: CurrentUser, db: DBSession) -> dict[str, bool]:
    _require_enabled()
    try: world_service.delete_item(db, Prop, user.id, project_id, item_id); return {"deleted": True}
    except (project_service.ProjectNotFoundError, world_service.WorldValidationError) as exc: raise _screenplay_error(exc)


@router.post("/projects/{project_id}/relationships", response_model=RelationshipOut, status_code=status.HTTP_201_CREATED)
def create_relationship(project_id: int, body: RelationshipInput, user: CurrentUser, db: DBSession) -> RelationshipOut:
    _require_enabled()
    try: return RelationshipOut.model_validate(world_service.save_relationship(db, user.id, project_id, body))
    except (project_service.ProjectNotFoundError, world_service.WorldValidationError) as exc: raise _screenplay_error(exc)


@router.put("/projects/{project_id}/relationships/{item_id}", response_model=RelationshipOut)
def update_relationship(project_id: int, item_id: int, body: RelationshipInput, user: CurrentUser, db: DBSession) -> RelationshipOut:
    _require_enabled()
    try: return RelationshipOut.model_validate(world_service.save_relationship(db, user.id, project_id, body, item_id))
    except (project_service.ProjectNotFoundError, world_service.WorldValidationError) as exc: raise _screenplay_error(exc)


@router.delete("/projects/{project_id}/relationships/{item_id}")
def delete_relationship(project_id: int, item_id: int, user: CurrentUser, db: DBSession) -> dict[str, bool]:
    _require_enabled()
    try: world_service.delete_item(db, CharacterRelationship, user.id, project_id, item_id); return {"deleted": True}
    except (project_service.ProjectNotFoundError, world_service.WorldValidationError) as exc: raise _screenplay_error(exc)


@router.get("/resources/{resource_id}/usages", response_model=ResourceUsageOut)
def get_resource_usages(resource_id: int, user: CurrentUser, db: DBSession) -> ResourceUsageOut:
    _require_enabled()
    try: usages = world_service.resource_usages(db, user.id, resource_id)
    except project_service.ProjectNotFoundError as exc: raise _screenplay_error(exc)
    return ResourceUsageOut(resource_id=resource_id, usages=usages)


@router.get("/projects/{project_id}/storyboard", response_model=StoryboardOut)
def get_storyboard(project_id: int, user: CurrentUser, db: DBSession) -> StoryboardOut:
    _require_enabled()
    try: project, episodes, by_scene = storyboard_service.overview(db, user.id, project_id)
    except project_service.ProjectNotFoundError as exc: raise _screenplay_error(exc)
    episode_outputs: list[StoryboardEpisodeOut] = []; total_shots = 0; ready_shots = 0; total_duration = 0.0
    for episode in episodes:
        scene_outputs: list[StoryboardSceneOut] = []
        for scene in episode.scenes:
            shots = by_scene.get(scene.id, []); duration = round(sum(item.duration for item in shots), 2); target = storyboard_service._duration_target(db, scene)
            scene_blockers = sorted({message for item in shots for message in storyboard_service.blockers(db, item)})
            scene_outputs.append(StoryboardSceneOut(scene=SceneOut.model_validate(scene), shots=[ShotOut.model_validate(item) for item in shots], shot_duration=duration, target_duration=target, duration_delta=round(duration-target, 2), blockers=scene_blockers))
            total_shots += len(shots); ready_shots += sum(item.status == "ready" for item in shots); total_duration += duration
        episode_outputs.append(StoryboardEpisodeOut(episode=EpisodeOut.model_validate(episode), scenes=scene_outputs))
    return StoryboardOut(project=ProjectOut.model_validate(project), episodes=episode_outputs, total_shots=total_shots, ready_shots=ready_shots, total_duration=round(total_duration, 2))


@router.post("/projects/{project_id}/scenes/{scene_id}/shot-candidates", response_model=StoryboardCandidateOut, status_code=status.HTTP_201_CREATED)
def create_shot_candidate(project_id: int, scene_id: int, body: StoryboardCandidateCreateIn, user: CurrentUser, db: DBSession) -> StoryboardCandidateOut:
    _require_enabled()
    try: return StoryboardCandidateOut.model_validate(storyboard_service.create_candidate(db, user.id, project_id, scene_id, body.story_version_id))
    except (project_service.ProjectNotFoundError, storyboard_service.StoryboardValidationError) as exc: raise _screenplay_error(exc)


@router.post("/projects/{project_id}/shot-candidates/{candidate_id}/confirm", response_model=StoryboardCandidateOut)
def confirm_shot_candidate(project_id: int, candidate_id: int, body: StoryboardCandidateConfirmIn, user: CurrentUser, db: DBSession) -> StoryboardCandidateOut:
    _require_enabled()
    try: return StoryboardCandidateOut.model_validate(storyboard_service.confirm_candidate(db, user.id, project_id, candidate_id, body.mode))
    except (project_service.ProjectNotFoundError, storyboard_service.StoryboardValidationError) as exc: raise _screenplay_error(exc)


@router.post("/projects/{project_id}/scenes/{scene_id}/shots", response_model=ShotOut, status_code=status.HTTP_201_CREATED)
def create_shot(project_id: int, scene_id: int, body: ShotInput, user: CurrentUser, db: DBSession) -> ShotOut:
    _require_enabled()
    try: return ShotOut.model_validate(storyboard_service.create_shot(db, user.id, project_id, scene_id, body))
    except (project_service.ProjectNotFoundError, storyboard_service.StoryboardValidationError) as exc: raise _screenplay_error(exc)


@router.put("/projects/{project_id}/shots/{shot_id}", response_model=ShotOut)
def update_shot(project_id: int, shot_id: int, body: ShotPatchIn, user: CurrentUser, db: DBSession) -> ShotOut:
    _require_enabled()
    try: return ShotOut.model_validate(storyboard_service.update_shot(db, user.id, project_id, shot_id, body))
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError, storyboard_service.StoryboardValidationError) as exc: raise _screenplay_error(exc)


@router.delete("/projects/{project_id}/shots/{shot_id}")
def delete_shot(project_id: int, shot_id: int, user: CurrentUser, db: DBSession) -> dict[str, bool]:
    _require_enabled()
    try: storyboard_service.delete_shot(db, user.id, project_id, shot_id); return {"deleted": True}
    except (project_service.ProjectNotFoundError, storyboard_service.StoryboardValidationError) as exc: raise _screenplay_error(exc)


@router.post("/projects/{project_id}/shots/{shot_id}/copy", response_model=ShotOut, status_code=status.HTTP_201_CREATED)
def copy_shot(project_id: int, shot_id: int, user: CurrentUser, db: DBSession) -> ShotOut:
    _require_enabled()
    try: return ShotOut.model_validate(storyboard_service.copy_shot(db, user.id, project_id, shot_id))
    except (project_service.ProjectNotFoundError, storyboard_service.StoryboardValidationError) as exc: raise _screenplay_error(exc)


@router.post("/projects/{project_id}/shots/{shot_id}/split", response_model=list[ShotOut])
def split_shot(project_id: int, shot_id: int, body: ShotSplitIn, user: CurrentUser, db: DBSession) -> list[ShotOut]:
    _require_enabled()
    try: return [ShotOut.model_validate(item) for item in storyboard_service.split_shot(db, user.id, project_id, shot_id, body.split_ratio)]
    except (project_service.ProjectNotFoundError, storyboard_service.StoryboardValidationError) as exc: raise _screenplay_error(exc)


@router.post("/projects/{project_id}/shots/merge", response_model=ShotOut)
def merge_shots(project_id: int, body: ShotMergeIn, user: CurrentUser, db: DBSession) -> ShotOut:
    _require_enabled()
    try: return ShotOut.model_validate(storyboard_service.merge_shots(db, user.id, project_id, body.shot_ids))
    except (project_service.ProjectNotFoundError, storyboard_service.StoryboardValidationError) as exc: raise _screenplay_error(exc)


@router.put("/projects/{project_id}/scenes/{scene_id}/shots/reorder", response_model=list[ShotOut])
def reorder_shots(project_id: int, scene_id: int, body: ShotReorderIn, user: CurrentUser, db: DBSession) -> list[ShotOut]:
    _require_enabled()
    try: return [ShotOut.model_validate(item) for item in storyboard_service.reorder(db, user.id, project_id, scene_id, body.shot_ids)]
    except (project_service.ProjectNotFoundError, storyboard_service.StoryboardValidationError) as exc: raise _screenplay_error(exc)


@router.patch("/projects/{project_id}/shots/bulk", response_model=list[ShotOut])
def bulk_patch_shots(project_id: int, body: ShotBulkPatchIn, user: CurrentUser, db: DBSession) -> list[ShotOut]:
    _require_enabled()
    try: return [ShotOut.model_validate(item) for item in storyboard_service.bulk_patch(db, user.id, project_id, body)]
    except (project_service.ProjectNotFoundError, storyboard_service.StoryboardValidationError) as exc: raise _screenplay_error(exc)


@router.post("/projects/{project_id}/production/compile", response_model=list[CompiledShotTaskOut])
def compile_shot_tasks(
    project_id: int, body: ShotProductionCompileIn, user: CurrentUser, db: DBSession,
) -> list[CompiledShotTaskOut]:
    _require_enabled()
    try:
        return [CompiledShotTaskOut.model_validate(item) for item in production_service.compile_tasks(db, user.id, project_id, body)]
    except (project_service.ProjectNotFoundError, production_service.ProductionValidationError) as exc:
        raise _screenplay_error(exc)


@router.post(
    "/projects/{project_id}/production/tasks",
    response_model=ShotProductionCreateOut,
    status_code=status.HTTP_201_CREATED,
)
def create_shot_tasks(
    project_id: int, body: ShotProductionCreateIn, user: CurrentUser, db: DBSession,
) -> ShotProductionCreateOut:
    _require_enabled()
    try:
        batch, created, existing, links = production_service.create_tasks(db, user.id, project_id, body)
    except (project_service.ProjectNotFoundError, production_service.ProductionValidationError) as exc:
        raise _screenplay_error(exc)
    return ShotProductionCreateOut(
        batch_id=batch.id if batch else None,
        created_task_ids=[item.id for item in created],
        existing_task_ids=[item.id for item in existing],
        links=[ShotTaskLinkOut.model_validate(item) for item in links],
        submitted=body.submit,
    )


@router.get("/projects/{project_id}/shots/{shot_id}/production", response_model=ShotProductionOut)
def get_shot_production(project_id: int, shot_id: int, user: CurrentUser, db: DBSession) -> ShotProductionOut:
    _require_enabled()
    try:
        shot, tasks, takes = production_service.production_overview(db, user.id, project_id, shot_id)
    except project_service.ProjectNotFoundError as exc:
        raise _screenplay_error(exc)
    return ShotProductionOut(shot=ShotOut.model_validate(shot), tasks=tasks, takes=takes)


@router.post("/projects/{project_id}/tasks/{task_id}/reconcile", response_model=list[TakeOut])
def reconcile_shot_task(project_id: int, task_id: int, user: CurrentUser, db: DBSession) -> list[TakeOut]:
    _require_enabled()
    try:
        project_service.owned_project(db, user.id, project_id)
        link = db.query(ShotTaskLink).filter_by(owner_id=user.id, task_id=task_id).first()
        if not link:
            raise project_service.ProjectNotFoundError("镜头任务不存在")
        production_service._shot_context(db, user.id, project_id, link.shot_id)
        production_service.reconcile_task_outputs(db, task_id)
        _, _, takes = production_service.production_overview(db, user.id, project_id, link.shot_id)
        return [TakeOut.model_validate(item) for item in takes]
    except (project_service.ProjectNotFoundError, production_service.ProductionValidationError) as exc:
        raise _screenplay_error(exc)


@router.post("/projects/{project_id}/takes/{take_id}/select", response_model=TakeOut)
def select_take(project_id: int, take_id: int, user: CurrentUser, db: DBSession) -> TakeOut:
    _require_enabled()
    try: take = production_service.select_take(db, user.id, project_id, take_id, True)
    except (project_service.ProjectNotFoundError, production_service.ProductionValidationError) as exc: raise _screenplay_error(exc)
    return TakeOut.model_validate(production_service._take_out(db, take))


@router.post("/projects/{project_id}/takes/{take_id}/unselect", response_model=TakeOut)
def unselect_take(project_id: int, take_id: int, user: CurrentUser, db: DBSession) -> TakeOut:
    _require_enabled()
    try: take = production_service.select_take(db, user.id, project_id, take_id, False)
    except (project_service.ProjectNotFoundError, production_service.ProductionValidationError) as exc: raise _screenplay_error(exc)
    return TakeOut.model_validate(production_service._take_out(db, take))


@router.patch("/projects/{project_id}/takes/{take_id}/review", response_model=TakeOut)
def review_take(project_id: int, take_id: int, body: TakeReviewIn, user: CurrentUser, db: DBSession) -> TakeOut:
    _require_enabled()
    try: take = production_service.review_take(db, user.id, project_id, take_id, body.review_note)
    except (project_service.ProjectNotFoundError, production_service.ProductionValidationError) as exc: raise _screenplay_error(exc)
    return TakeOut.model_validate(production_service._take_out(db, take))


@router.delete("/projects/{project_id}/takes/{take_id}")
def delete_take(project_id: int, take_id: int, user: CurrentUser, db: DBSession) -> dict[str, bool]:
    _require_enabled()
    try: production_service.delete_take(db, user.id, project_id, take_id)
    except (project_service.ProjectNotFoundError, production_service.ProductionValidationError) as exc: raise _screenplay_error(exc)
    return {"deleted": True}


@router.post("/projects/{project_id}/takes/{take_id}/regenerate", response_model=dict)
def regenerate_take(
    project_id: int, take_id: int, body: TakeRegenerateIn, user: CurrentUser, db: DBSession,
) -> dict:
    _require_enabled()
    try:
        task, link = production_service.regenerate_take(
            db, user.id, project_id, take_id, body.review_note, body.parameter_overrides, body.idempotency_key
        )
    except (project_service.ProjectNotFoundError, production_service.ProductionValidationError) as exc:
        raise _screenplay_error(exc)
    return {"task_id": task.id, "link": ShotTaskLinkOut.model_validate(link).model_dump(mode="json")}


@router.post("/projects/{project_id}/episodes/{episode_id}/manifests/{manifest_id}/split-preview")
def preview_manifest_split(project_id: int, episode_id: int, manifest_id: int, body: ScriptManifestSplitIn, user: CurrentUser, db: DBSession):
    _require_enabled()
    from app.short_drama.manifest_editing import edit_split
    try: return edit_split(db, user.id, project_id, episode_id, manifest_id, body)
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError) as exc: raise _not_found_or_conflict(exc)


@router.post("/projects/{project_id}/episodes/{episode_id}/manifests/{manifest_id}/split-apply", response_model=ScriptManifestOut)
def apply_manifest_split(project_id: int, episode_id: int, manifest_id: int, body: ScriptManifestSplitIn, user: CurrentUser, db: DBSession):
    _require_enabled()
    from app.short_drama.manifest_editing import edit_split
    try: return edit_split(db, user.id, project_id, episode_id, manifest_id, body, apply=True)
    except (project_service.ProjectNotFoundError, project_service.ProjectConflictError) as exc: raise _not_found_or_conflict(exc)
