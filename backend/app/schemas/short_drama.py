"""V2.1 短剧项目与创作简报 API Schema。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


SourceType = Literal["idea", "outline", "script", "novel"]
ProjectStatus = Literal["draft", "active", "paused", "completed", "archived"]
QualityTier = Literal["draft", "standard", "final"]


class ProjectBriefInput(BaseModel):
    genre: str = Field(default="", max_length=64)
    audience: str = Field(default="", max_length=128)
    tone: str = Field(default="", max_length=128)
    platform: str = Field(default="", max_length=64)
    aspect_ratio: str = Field(default="9:16", max_length=16)
    episode_count: int = Field(default=1, ge=1, le=999)
    episode_duration: int = Field(default=60, ge=1, le=7200)
    quality_tier: QualityTier = "draft"
    visual_style: str = Field(default="", max_length=4000)
    constraints: dict[str, Any] = Field(default_factory=dict)


class ProjectCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    synopsis: str = Field(default="", max_length=10000)
    source_type: SourceType = "idea"
    brief: ProjectBriefInput = Field(default_factory=ProjectBriefInput)


class ProjectPatchIn(BaseModel):
    lock_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    synopsis: str | None = Field(default=None, max_length=10000)
    status: ProjectStatus | None = None
    stage: str | None = Field(default=None, min_length=1, max_length=32)


class ProjectBriefPatchIn(ProjectBriefInput):
    lock_version: int = Field(ge=1)


class ProjectBriefOut(ProjectBriefInput):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    project_id: int
    lock_version: int
    created_at: datetime
    updated_at: datetime


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    name: str
    synopsis: str
    source_type: str
    status: str
    stage: str
    cover_resource_id: int | None
    settings: dict[str, Any]
    lock_version: int
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProjectSummaryOut(ProjectOut):
    episode_count: int = 0
    scene_count: int = 0
    shot_count: int = 0


class ProjectListOut(BaseModel):
    items: list[ProjectSummaryOut]
    total: int
    page: int
    page_size: int


class ProjectOverviewOut(BaseModel):
    project: ProjectOut
    brief: ProjectBriefOut
    episode_count: int
    scene_count: int
    shot_count: int
    take_count: int
    selected_take_count: int
    creative_job_count: int
    active_job_count: int


class ProjectQuickCreateIn(ProjectCreateIn):
    episode_title: str = Field(default="第 1 集", min_length=1, max_length=160)


class ProjectQuickCreateOut(BaseModel):
    project: ProjectOut
    episode_id: int


class SourceDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    project_id: int
    resource_id: int
    filename: str
    source_format: str
    title: str
    encoding: str | None
    status: str
    total_chapters: int
    total_paragraphs: int
    total_chars: int
    error: str | None
    created_at: datetime
    updated_at: datetime


class CreativeJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    project_id: int | None
    job_type: str
    status: str
    progress: int
    input_payload: dict[str, Any]
    output_payload: dict[str, Any]
    logs: list[dict[str, Any]]
    error: str | None
    retries: int
    heartbeat_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    cancelled_at: datetime | None
    parent_job_id: int | None = None
    provider_config_id: int | None = None
    prompt_template_id: int | None = None
    model: str | None = None
    token_usage: dict[str, Any] = Field(default_factory=dict)
    estimated_cost: float = 0
    created_at: datetime
    updated_at: datetime


class CreativeJobListOut(BaseModel):
    items: list[CreativeJobOut]
    total: int
    page: int
    page_size: int


class DocumentImportOut(BaseModel):
    document: SourceDocumentOut
    job: CreativeJobOut


class AIProviderInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    provider: str = Field(default="openai_compatible", pattern="^openai_compatible$")
    base_url: str = Field(min_length=1, max_length=512)
    model: str = Field(min_length=1, max_length=128)
    api_key: str | None = Field(default=None, max_length=2048)
    enabled: bool = True
    is_default: bool = False
    timeout_seconds: int = Field(default=120, ge=5, le=600)
    max_tokens: int = Field(default=8192, ge=256, le=131072)


class AIProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; name: str; provider: str; base_url: str; model: str; api_key_hint: str
    enabled: bool; is_default: bool; timeout_seconds: int; max_tokens: int
    created_at: datetime; updated_at: datetime


class AIPromptTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; code: str; name: str; version: int
    system_prompt: str; user_prompt: str
    enabled: bool
    created_at: datetime; updated_at: datetime


class AIPromptTemplateUpdateIn(BaseModel):
    system_prompt: str = Field(min_length=1)
    user_prompt: str = Field(min_length=1)


class AIGenerationRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int | None = None
    operation: str
    model: str
    status: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float
    duration_ms: int
    error: str | None = None
    request_snapshot: dict[str, Any] = Field(default_factory=dict)
    response_snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    finished_at: datetime | None = None


class NovelAnalyzeIn(BaseModel):
    document_id: int
    chapter_start: int = Field(ge=1)
    chapter_end: int = Field(ge=1)
    provider_config_id: int | None = None
    idempotency_key: str = Field(min_length=1, max_length=80)


class AIAdaptationIn(BaseModel):
    analysis_id: int
    episode_count: int | None = Field(default=None, ge=1, le=999)
    strategies: list[str] = Field(default_factory=lambda: ["faithful", "high_tempo", "emotional"], min_length=1, max_length=5)
    provider_config_id: int | None = None
    idempotency_key: str = Field(min_length=1, max_length=80)


class NovelAnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; owner_id: int; project_id: int; document_id: int; generation_record_id: int | None
    version: int; status: str; chapter_start: int; chapter_end: int
    content: dict[str, Any]; validation_errors: list[dict[str, Any]]; confirmed_at: datetime | None
    created_at: datetime; updated_at: datetime


class SourceParagraphOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    paragraph_index: int
    text: str
    char_count: int
    source_locator: str


class SourceChapterContentOut(BaseModel):
    id: int
    number: int
    title: str | None
    char_count: int
    paragraphs: list[SourceParagraphOut]


class SourceContentOut(BaseModel):
    document: SourceDocumentOut
    chapters: list[SourceChapterContentOut]


class AdaptationCandidateCreateIn(BaseModel):
    document_id: int
    chapter_start: int = Field(ge=1)
    chapter_end: int = Field(ge=1)
    episode_count: int | None = Field(default=None, ge=1, le=100)


class AdaptationCandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    project_id: int
    document_id: int
    chapter_start: int
    chapter_end: int
    status: str
    options: list[dict[str, Any]]
    validation_errors: list[dict[str, Any]]
    confirmed_option: str | None
    confirmed_version_id: int | None
    created_at: datetime
    updated_at: datetime


class AdaptationConfirmIn(BaseModel):
    option_key: str = Field(min_length=1, max_length=32)
    version_name: str = Field(default="首版剧本", min_length=1, max_length=160)


class SceneCreateIn(BaseModel):
    heading: str = Field(default="新场景", max_length=255)
    location_name: str = Field(default="", max_length=160)
    time_of_day: str = Field(default="", max_length=64)
    interior_exterior: str = Field(default="", max_length=16)
    content: str = Field(default="", max_length=100000)
    elements: list[dict[str, Any]] = Field(default_factory=list)
    source_references: list[dict[str, Any]] = Field(default_factory=list)
    character_ids: list[int] = Field(default_factory=list)
    location_id: int | None = None
    purpose: str = Field(default="", max_length=4000)
    target_duration: int = Field(default=0, ge=0, le=7200)


class ScenePatchIn(BaseModel):
    lock_version: int = Field(ge=1)
    heading: str | None = Field(default=None, max_length=255)
    location_name: str | None = Field(default=None, max_length=160)
    time_of_day: str | None = Field(default=None, max_length=64)
    interior_exterior: str | None = Field(default=None, max_length=16)
    content: str | None = Field(default=None, max_length=100000)
    elements: list[dict[str, Any]] | None = None
    source_references: list[dict[str, Any]] | None = None
    character_ids: list[int] | None = None
    location_id: int | None = None
    purpose: str | None = Field(default=None, max_length=4000)
    target_duration: int | None = Field(default=None, ge=0, le=7200)


class SceneOut(SceneCreateIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    episode_id: int
    scene_no: str
    sort_order: int
    status: str
    lock_version: int
    created_at: datetime
    updated_at: datetime


class EpisodeCreateIn(BaseModel):
    title: str = Field(default="新分集", max_length=160)
    synopsis: str = Field(default="", max_length=10000)
    target_duration: int = Field(default=60, ge=1, le=7200)
    core_conflict: str = Field(default="", max_length=10000)
    emotional_arc: str = Field(default="", max_length=10000)
    opening_hook: str = Field(default="", max_length=10000)
    ending_hook: str = Field(default="", max_length=10000)


class EpisodePatchIn(BaseModel):
    lock_version: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=160)
    synopsis: str | None = Field(default=None, max_length=10000)
    target_duration: int | None = Field(default=None, ge=1, le=7200)
    core_conflict: str | None = Field(default=None, max_length=10000)
    emotional_arc: str | None = Field(default=None, max_length=10000)
    opening_hook: str | None = Field(default=None, max_length=10000)
    ending_hook: str | None = Field(default=None, max_length=10000)
    is_locked: bool | None = None


class EpisodeOut(EpisodeCreateIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    project_id: int
    number: int
    sort_order: int
    status: str
    is_locked: bool
    lock_version: int
    created_at: datetime
    updated_at: datetime
    scenes: list[SceneOut] = Field(default_factory=list)


class EpisodeScriptPatchIn(BaseModel):
    lock_version: int = Field(ge=1)
    mode: Literal["novel", "storyboard"]
    text: str = Field(default="", max_length=200000)
    settings: dict[str, Any] = Field(default_factory=dict)


class EpisodeScriptOut(BaseModel):
    episode_id: int
    project_id: int
    title: str
    mode: Literal["novel", "storyboard"]
    text: str
    settings: dict[str, Any]
    script_revision: int
    lock_version: int
    updated_at: datetime
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class ScriptManifestGenerateIn(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=128)
    provider_config_id: int | None = None


class ScriptManifestPatchIn(BaseModel):
    lock_version: int = Field(ge=1)
    summary: str | None = Field(default=None, max_length=10000)
    content: dict[str, Any] | None = None


class ScriptManifestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; owner_id: int; project_id: int; episode_id: int; version: int
    status: str; source_script_revision: int; mode: str; summary: str
    total_duration: float; content: dict[str, Any]; validation_errors: list[dict[str, Any]]
    lock_version: int; confirmed_at: datetime | None; created_at: datetime; updated_at: datetime


class ProjectAssetCopyOut(BaseModel):
    entity_type: str
    entity_id: int
    name: str


class ProjectAssetVersionCreateIn(BaseModel):
    resource_id: int | None = None
    source_task_id: int | None = None
    prompt: str = Field(default="", max_length=20000)
    generation_snapshot: dict[str, Any] = Field(default_factory=dict)


class ProjectAssetVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; owner_id: int; project_id: int; entity_type: str; entity_id: int; version: int
    resource_id: int | None; source_task_id: int | None; status: str; is_current: bool
    prompt: str; generation_snapshot: dict[str, Any]; created_at: datetime; updated_at: datetime


class ShotCharacterBindingIn(BaseModel):
    character_id: int
    variant_id: int | None = None


class ShotCharacterBindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; owner_id: int; shot_id: int; character_id: int; variant_id: int | None
    inheritance_source: str; created_at: datetime; updated_at: datetime


class EpisodeAIGenerateIn(BaseModel):
    provider_config_id: int | None = None
    instruction: str = Field(default="", max_length=4000)
    idempotency_key: str = Field(min_length=1, max_length=128)


class ScreenplayRevisionCandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    project_id: int
    episode_id: int
    generation_record_id: int | None
    base_lock_version: int
    status: str
    instruction: str
    content: dict[str, Any]
    validation_errors: list[dict[str, Any]]
    confirmed_version_id: int | None
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ScreenplayOut(BaseModel):
    project: ProjectOut
    episodes: list[EpisodeOut]
    current_version_id: int | None
    draft_changed: bool


class ScreenplayReorderIn(BaseModel):
    episode_ids: list[int]
    scene_ids_by_episode: dict[int, list[int]] = Field(default_factory=dict)


class StoryVersionCreateIn(BaseModel):
    name: str = Field(default="人工版本", min_length=1, max_length=160)


class StoryVersionRenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class StoryVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    project_id: int
    parent_version_id: int | None
    version: int
    name: str
    source: str
    summary: str
    content: dict[str, Any]
    is_current: bool
    created_at: datetime
    updated_at: datetime


class StoryVersionListOut(BaseModel):
    items: list[StoryVersionOut]


class WorldCandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; owner_id: int; project_id: int; story_version_id: int | None
    status: str; payload: dict[str, Any]; conflicts: list[dict[str, Any]]; confirmed_at: datetime | None
    created_at: datetime; updated_at: datetime


class WorldCandidateConfirmIn(BaseModel):
    skip_existing: bool = True


class CharacterInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    aliases: list[str] = Field(default_factory=list)
    identity: str = Field(default="", max_length=4000)
    age_appearance: str = Field(default="", max_length=128)
    appearance: str = Field(default="", max_length=10000)
    personality: str = Field(default="", max_length=10000)
    relationships: dict[str, Any] = Field(default_factory=dict)
    negative_traits: list[str] = Field(default_factory=list)
    source_references: list[dict[str, Any]] = Field(default_factory=list)
    reference_resource_ids: list[int] = Field(default_factory=list)
    primary_resource_id: int | None = None
    status: str = Field(default="draft", pattern="^(draft|confirmed)$")


class CharacterVariantInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=10000)
    wardrobe: str = Field(default="", max_length=10000)
    hairstyle: str = Field(default="", max_length=10000)
    makeup: str = Field(default="", max_length=10000)
    primary_resource_id: int | None = None
    reference_resource_ids: list[int] = Field(default_factory=list)
    source_references: list[dict[str, Any]] = Field(default_factory=list)
    status: str = Field(default="draft", pattern="^(draft|confirmed)$")
    version: int = Field(default=1, ge=1)
    is_default: bool = False


class CharacterVariantOut(CharacterVariantInput):
    model_config = ConfigDict(from_attributes=True)
    id: int; owner_id: int; character_id: int; created_at: datetime; updated_at: datetime


class CharacterOut(CharacterInput):
    model_config = ConfigDict(from_attributes=True)
    id: int; owner_id: int; project_id: int; created_at: datetime; updated_at: datetime
    variants: list[CharacterVariantOut] = Field(default_factory=list)


class LocationInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=10000)
    spatial_layout: str = Field(default="", max_length=10000)
    time_weather: str = Field(default="", max_length=255)
    lighting: str = Field(default="", max_length=10000)
    color_palette: list[str] = Field(default_factory=list)
    fixed_objects: list[str] = Field(default_factory=list)
    source_references: list[dict[str, Any]] = Field(default_factory=list)
    reference_resource_ids: list[int] = Field(default_factory=list)
    primary_resource_id: int | None = None
    status: str = Field(default="draft", pattern="^(draft|confirmed)$")


class LocationOut(LocationInput):
    model_config = ConfigDict(from_attributes=True)
    id: int; owner_id: int; project_id: int; created_at: datetime; updated_at: datetime


class PropInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=10000)
    appearance: str = Field(default="", max_length=10000)
    appearance_scope: str = Field(default="", max_length=255)
    owner_character_id: int | None = None
    continuity_note: str = Field(default="", max_length=10000)
    source_references: list[dict[str, Any]] = Field(default_factory=list)
    reference_resource_ids: list[int] = Field(default_factory=list)
    resource_id: int | None = None
    status: str = Field(default="draft", pattern="^(draft|confirmed)$")


class PropOut(PropInput):
    model_config = ConfigDict(from_attributes=True)
    id: int; owner_id: int; project_id: int; created_at: datetime; updated_at: datetime


class RelationshipInput(BaseModel):
    source_character_id: int; target_character_id: int
    relationship_type: str = Field(default="关联", max_length=64)
    description: str = Field(default="", max_length=10000)
    source_references: list[dict[str, Any]] = Field(default_factory=list)
    status: str = Field(default="draft", pattern="^(draft|confirmed)$")


class RelationshipOut(RelationshipInput):
    model_config = ConfigDict(from_attributes=True)
    id: int; owner_id: int; project_id: int; created_at: datetime; updated_at: datetime


class WorldOverviewOut(BaseModel):
    characters: list[CharacterOut]; locations: list[LocationOut]; props: list[PropOut]; relationships: list[RelationshipOut]


class PhaseOneCastingOut(BaseModel):
    characters: list[CharacterOut]
    locations: list[LocationOut]
    props: list[PropOut]
    asset_versions: list[ProjectAssetVersionOut]


class ResourceUsageOut(BaseModel):
    resource_id: int
    usages: list[dict[str, Any]]


class ShotInput(BaseModel):
    purpose: str = Field(default="", max_length=10000)
    visual_description: str = Field(default="", max_length=20000)
    action: str = Field(default="", max_length=10000)
    expression: str = Field(default="", max_length=255)
    dialogue: str = Field(default="", max_length=10000)
    timeline_storyboard: str = Field(default="", max_length=50000)
    video_prompt: str = Field(default="", max_length=50000)
    negative_prompt: str = Field(default="", max_length=20000)
    continuity: str = Field(default="", max_length=20000)
    character_ids: list[int] = Field(default_factory=list)
    location_id: int | None = None
    prop_ids: list[int] = Field(default_factory=list)
    mood: str = Field(default="", max_length=255)
    shot_size: str = Field(default="中景", max_length=64)
    camera_angle: str = Field(default="平视", max_length=64)
    camera_movement: str = Field(default="固定", max_length=128)
    composition: str = Field(default="", max_length=255)
    transition: str = Field(default="", max_length=128)
    duration: float = Field(default=3, ge=0.1, le=600)
    first_frame_resource_id: int | None = None
    last_frame_resource_id: int | None = None
    pose_resource_id: int | None = None
    reference_video_resource_id: int | None = None
    reference_audio_resource_id: int | None = None
    reference_resource_ids: list[int] = Field(default_factory=list)
    status: str = Field(default="draft", pattern="^(draft|ready)$")
    production_settings: dict[str, Any] = Field(default_factory=dict)


class ShotPatchIn(ShotInput):
    lock_version: int = Field(ge=1)


class ShotOut(ShotInput):
    model_config = ConfigDict(from_attributes=True)
    id: int; owner_id: int; scene_id: int; source_story_version_id: int | None
    shot_no: int; sort_order: int; lock_version: int; created_at: datetime; updated_at: datetime


class StoryboardCandidateCreateIn(BaseModel):
    story_version_id: int | None = None


class StoryboardCandidateConfirmIn(BaseModel):
    mode: str = Field(default="replace_drafts", pattern="^(replace_drafts|append)$")


class StoryboardCandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; owner_id: int; project_id: int; scene_id: int; story_version_id: int
    status: str; payload: dict[str, Any]; validation_warnings: list[dict[str, Any]]
    confirmed_mode: str | None; confirmed_at: datetime | None; created_at: datetime; updated_at: datetime


class ShotReorderIn(BaseModel):
    shot_ids: list[int]


class ShotSplitIn(BaseModel):
    split_ratio: float = Field(default=0.5, gt=0.05, lt=0.95)


class ShotMergeIn(BaseModel):
    shot_ids: list[int] = Field(min_length=2)


class ShotBulkPatchIn(BaseModel):
    shot_ids: list[int] = Field(min_length=1)
    duration: float | None = Field(default=None, ge=0.1, le=600)
    status: str | None = Field(default=None, pattern="^(draft|ready)$")
    aspect_ratio: str | None = None
    quality_tier: str | None = None


class StoryboardSceneOut(BaseModel):
    scene: SceneOut
    shots: list[ShotOut]
    shot_duration: float
    target_duration: float
    duration_delta: float
    blockers: list[str]


class StoryboardEpisodeOut(BaseModel):
    episode: EpisodeOut
    scenes: list[StoryboardSceneOut]


class StoryboardOut(BaseModel):
    project: ProjectOut
    episodes: list[StoryboardEpisodeOut]
    total_shots: int
    ready_shots: int
    total_duration: float


class ShotProductionCompileIn(BaseModel):
    shot_ids: list[int] = Field(min_length=1, max_length=200)
    generation_type_id: int
    workflow_version_id: int | None = None
    parameter_overrides: dict[str, Any] = Field(default_factory=dict)
    shot_parameter_overrides: dict[int, dict[str, Any]] = Field(default_factory=dict)


class CompiledShotTaskOut(BaseModel):
    shot_id: int
    generation_type_id: int
    generation_type_name: str
    media_type: str
    workflow_version_id: int
    workflow_name: str
    params: dict[str, Any]
    prompt: str
    input_resource_ids: list[int]
    validation_errors: list[dict[str, Any]]
    validation_warnings: list[dict[str, Any]]


class ShotProductionCreateIn(ShotProductionCompileIn):
    idempotency_key: str = Field(min_length=1, max_length=80)
    submit: bool = True
    save_as_project_default: bool = False


class ShotTaskLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; owner_id: int; shot_id: int; task_id: int; take_id: int | None
    purpose: str; status: str; idempotency_key: str; output_payload: dict[str, Any]
    sync_error: str | None; sync_attempts: int; next_retry_at: datetime | None
    created_at: datetime; updated_at: datetime


class ShotProductionCreateOut(BaseModel):
    batch_id: int | None
    created_task_ids: list[int]
    existing_task_ids: list[int]
    links: list[ShotTaskLinkOut]
    submitted: bool


class TakeResourceOut(BaseModel):
    id: int; filename: str; media_type: str; mime: str; width: int | None
    height: int | None; duration: int | None; size: int


class TakeOut(BaseModel):
    id: int; owner_id: int; shot_id: int; resource_id: int; source_task_id: int | None
    take_no: int; status: str; is_selected: bool; generation_snapshot: dict[str, Any]
    review_note: str; resource: TakeResourceOut; created_at: datetime; updated_at: datetime


class ShotTaskStatusOut(BaseModel):
    link: ShotTaskLinkOut
    task_status: str
    task_error: str | None
    generation_type_id: int | None
    workflow_version_id: int | None
    params: dict[str, Any]
    created_at: datetime


class ShotProductionOut(BaseModel):
    shot: ShotOut
    tasks: list[ShotTaskStatusOut]
    takes: list[TakeOut]


class TakeReviewIn(BaseModel):
    review_note: str = Field(default="", max_length=10000)


class TakeRegenerateIn(BaseModel):
    review_note: str = Field(default="", max_length=10000)
    parameter_overrides: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=80)


class ScriptManifestSplitIn(BaseModel):
    lock_version: int = Field(ge=1)
    scene_index: int = Field(ge=0)
    shot_index: int = Field(ge=0)
    preview_hash: str | None = None
