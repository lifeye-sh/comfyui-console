from typing import Any, Literal
from pydantic import BaseModel, Field

class FrameDraft(BaseModel):
    id: str = Field(pattern=r"^(start|end|key_[a-zA-Z0-9_-]{1,40})$")
    kind: Literal["start", "key", "end"]
    time: float = Field(default=0, ge=0, le=3600)
    prompt: str = Field(default="", max_length=20000)
    workflow_version_id: int | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    generation_service: Literal["comfyui", "gemini_image"] = "comfyui"
    gemini_provider_id: int | None = None
    gemini_params: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    order: int = Field(default=0, ge=0, le=9999)

class CharacterAssetChoice(BaseModel):
    """Per-shot character presentation source: base image or three-view turnaround.
    Costume variant binding lives in shot_character_bindings (refs API), not here."""
    character_id: int
    image_mode: Literal["primary", "turnaround"] = "primary"
    enabled: bool = True
    order: int = Field(default=0, ge=0, le=9999)

class ExtraResourceItem(BaseModel):
    """Library resource attached to the shot: image / audio / video.
    Only checked items feed workflow inputs, ordered by the check sequence."""
    resource_id: int
    media_type: Literal["image", "audio", "video"]
    label: str = Field(default="", max_length=200)
    enabled: bool = True
    order: int = Field(default=0, ge=0, le=9999)

class AssetChoices(BaseModel):
    """Video resource package edited on the make page: extras plus character modes.
    All three groups (frames / extras / context assets) share one check-order space."""
    extras: list[ExtraResourceItem] = Field(default_factory=list)
    characters: list[CharacterAssetChoice] = Field(default_factory=list)
    location_enabled: bool = False
    location_order: int = Field(default=0, ge=0, le=9999)
    prop_orders: dict[str, int] = Field(default_factory=dict)  # prop_id -> order; present = checked

class VideoPromptInputs(BaseModel):
    visual_description: str | None = Field(default=None, max_length=20000)
    visual_style: str | None = Field(default=None, max_length=20000)
    action: str | None = Field(default=None, max_length=20000)
    expression: str | None = Field(default=None, max_length=20000)
    dialogue: str | None = Field(default=None, max_length=20000)
    timeline_storyboard: str | None = Field(default=None, max_length=50000)
    continuity: str | None = Field(default=None, max_length=20000)
    shot_size: str | None = Field(default=None, max_length=2000)
    camera_angle: str | None = Field(default=None, max_length=2000)
    camera_movement: str | None = Field(default=None, max_length=2000)
    composition: str | None = Field(default=None, max_length=20000)
    transition: str | None = Field(default=None, max_length=2000)
    atmosphere: str | None = Field(default=None, max_length=20000)
    negative_constraints: str | None = Field(default=None, max_length=20000)

class WorkspaceDraft(BaseModel):
    frames: list[FrameDraft] = Field(min_length=1, max_length=30)
    prompt_inputs: VideoPromptInputs = Field(default_factory=VideoPromptInputs)
    prompt_input_overrides: list[str] = Field(default_factory=list)
    prompt_asset_descriptions: dict[str, str] = Field(default_factory=dict)
    video_prompt: str = Field(default="", max_length=20000)
    video_workflow_version_id: int | None = None
    video_mode: Literal["manual", "first", "first_last", "references"] = "manual"
    video_params: dict[str, Any] = Field(default_factory=dict)
    asset_choices: AssetChoices = Field(default_factory=AssetChoices)

class WorkspaceSave(BaseModel):
    revision: int = Field(ge=1)
    draft: WorkspaceDraft

class WorkflowBinding(BaseModel):
    mapping: dict[str, str] = Field(default_factory=dict)

class DirectorGenerate(BaseModel):
    scope: str = Field(pattern=r"^(video|start|end|key_[a-zA-Z0-9_-]{1,40})$")
    workflow_version_id: int | None = None
    generation_service: Literal["comfyui", "gemini_image"] = "comfyui"
    provider_config_id: int | None = None
    mode: Literal["manual", "first", "first_last", "references"] = "manual"
    params: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=8, max_length=80)
    expected_fingerprint: str | None = None

class ImportFrame(BaseModel):
    scope: str = Field(pattern=r"^(start|end|key_[a-zA-Z0-9_-]{1,40})$")
    resource_id: int

class ShotRefsUpdate(BaseModel):
    """Bind characters (with costume variant) / location / props onto the shot."""
    character_ids: list[int] = Field(default_factory=list)
    bindings: dict[str, int | None] = Field(default_factory=dict)  # character_id -> variant_id
    location_id: int | None = None
    prop_ids: list[int] = Field(default_factory=list)
