"""V2.1 AI 短剧领域模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ShortDramaProject(Base, TimestampMixin):
    __tablename__ = "short_drama_projects"
    __table_args__ = (Index("ix_drama_projects_owner_status", "owner_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    synopsis: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="idea", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(32), default="brief", nullable=False)
    cover_resource_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("resources.id", ondelete="SET NULL"), nullable=True
    )
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    lock_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    brief: Mapped[Optional["ProjectBrief"]] = relationship(back_populates="project", uselist=False)
    episodes: Mapped[list["Episode"]] = relationship(back_populates="project", order_by="Episode.sort_order")
    characters: Mapped[list["Character"]] = relationship(back_populates="project")
    locations: Mapped[list["Location"]] = relationship(back_populates="project")
    props: Mapped[list["Prop"]] = relationship(back_populates="project")
    story_versions: Mapped[list["StoryVersion"]] = relationship(
        back_populates="project", foreign_keys="StoryVersion.project_id", order_by="StoryVersion.version"
    )
    source_documents: Mapped[list["SourceDocument"]] = relationship(
        back_populates="project", order_by="SourceDocument.id"
    )


class ProjectBrief(Base, TimestampMixin):
    __tablename__ = "project_briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    genre: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    audience: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    tone: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    platform: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    aspect_ratio: Mapped[str] = mapped_column(String(16), default="9:16", nullable=False)
    episode_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    episode_duration: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    quality_tier: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    visual_style: Mapped[str] = mapped_column(Text, default="", nullable=False)
    constraints: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    lock_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    project: Mapped["ShortDramaProject"] = relationship(back_populates="brief")


class Episode(Base, TimestampMixin):
    __tablename__ = "drama_episodes"
    __table_args__ = (
        UniqueConstraint("project_id", "number", name="uq_drama_episode_project_number"),
        Index("ix_drama_episodes_project_order", "project_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    synopsis: Mapped[str] = mapped_column(Text, default="", nullable=False)
    target_duration: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    core_conflict: Mapped[str] = mapped_column(Text, default="", nullable=False)
    emotional_arc: Mapped[str] = mapped_column(Text, default="", nullable=False)
    opening_hook: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ending_hook: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False, index=True)
    lock_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    project: Mapped["ShortDramaProject"] = relationship(back_populates="episodes")
    scenes: Mapped[list["Scene"]] = relationship(back_populates="episode", order_by="Scene.sort_order")


class Scene(Base, TimestampMixin):
    __tablename__ = "drama_scenes"
    __table_args__ = (Index("ix_drama_scenes_episode_order", "episode_id", "sort_order"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    episode_id: Mapped[int] = mapped_column(Integer, ForeignKey("drama_episodes.id", ondelete="CASCADE"), nullable=False)
    scene_no: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    heading: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    location_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    time_of_day: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    interior_exterior: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    elements: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    source_references: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    character_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    location_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("drama_locations.id", ondelete="SET NULL"), nullable=True)
    purpose: Mapped[str] = mapped_column(Text, default="", nullable=False)
    target_duration: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False, index=True)
    lock_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    episode: Mapped["Episode"] = relationship(back_populates="scenes")
    shots: Mapped[list["Shot"]] = relationship(back_populates="scene", order_by="Shot.sort_order")


class StoryVersion(Base, TimestampMixin):
    __tablename__ = "story_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_story_version_project_version"),
        Index(
            "uq_story_version_current_per_project",
            "project_id",
            unique=True,
            sqlite_where=text("is_current = 1"),
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_version_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("story_versions.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    project: Mapped["ShortDramaProject"] = relationship(
        back_populates="story_versions", foreign_keys=[project_id]
    )
    parent: Mapped[Optional["StoryVersion"]] = relationship(remote_side=[id])


class Shot(Base, TimestampMixin):
    __tablename__ = "drama_shots"
    __table_args__ = (
        Index("ix_drama_shots_scene_order", "scene_id", "sort_order"),
        Index("uq_drama_shots_scene_no", "scene_id", "shot_no", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    scene_id: Mapped[int] = mapped_column(Integer, ForeignKey("drama_scenes.id", ondelete="CASCADE"), nullable=False)
    source_story_version_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("story_versions.id"), nullable=True)
    shot_no: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, default="", nullable=False)
    visual_description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    action: Mapped[str] = mapped_column(Text, default="", nullable=False)
    expression: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    dialogue: Mapped[str] = mapped_column(Text, default="", nullable=False)
    character_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    location_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("drama_locations.id", ondelete="SET NULL"), nullable=True)
    prop_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    mood: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    shot_size: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    camera_angle: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    camera_movement: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    composition: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    transition: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    duration: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    first_frame_resource_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    last_frame_resource_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    pose_resource_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    reference_video_resource_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    reference_audio_resource_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    reference_resource_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False, index=True)
    production_settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    lock_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    scene: Mapped["Scene"] = relationship(back_populates="shots")
    story_version: Mapped[Optional["StoryVersion"]] = relationship()
    takes: Mapped[list["Take"]] = relationship(back_populates="shot", order_by="Take.take_no")


class StoryboardCandidate(Base, TimestampMixin):
    __tablename__ = "storyboard_candidates"
    __table_args__ = (Index("ix_storyboard_candidates_scene_status", "scene_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    scene_id: Mapped[int] = mapped_column(Integer, ForeignKey("drama_scenes.id", ondelete="CASCADE"), nullable=False, index=True)
    story_version_id: Mapped[int] = mapped_column(Integer, ForeignKey("story_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    validation_warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    confirmed_mode: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Take(Base, TimestampMixin):
    __tablename__ = "drama_takes"
    __table_args__ = (
        UniqueConstraint("shot_id", "take_no", name="uq_drama_take_shot_number"),
        Index(
            "uq_drama_take_selected_per_shot",
            "shot_id",
            unique=True,
            sqlite_where=text("is_selected = 1"),
            postgresql_where=text("is_selected"),
        ),
        Index("uq_drama_take_task_resource", "source_task_id", "resource_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    shot_id: Mapped[int] = mapped_column(Integer, ForeignKey("drama_shots.id", ondelete="CASCADE"), nullable=False)
    resource_id: Mapped[int] = mapped_column(Integer, ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False)
    source_task_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    take_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="candidate", nullable=False, index=True)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    generation_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    review_note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    shot: Mapped["Shot"] = relationship(back_populates="takes")


class Character(Base, TimestampMixin):
    __tablename__ = "drama_characters"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_drama_character_project_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    identity: Mapped[str] = mapped_column(Text, default="", nullable=False)
    age_appearance: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    appearance: Mapped[str] = mapped_column(Text, default="", nullable=False)
    personality: Mapped[str] = mapped_column(Text, default="", nullable=False)
    relationships: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    negative_traits: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source_references: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    reference_resource_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    primary_resource_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("resources.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)

    project: Mapped["ShortDramaProject"] = relationship(back_populates="characters")
    variants: Mapped[list["CharacterVariant"]] = relationship(back_populates="character")


class CharacterVariant(Base, TimestampMixin):
    __tablename__ = "character_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    character_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("drama_characters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    wardrobe: Mapped[str] = mapped_column(Text, default="", nullable=False)
    hairstyle: Mapped[str] = mapped_column(Text, default="", nullable=False)
    makeup: Mapped[str] = mapped_column(Text, default="", nullable=False)
    primary_resource_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("resources.id", ondelete="SET NULL"), nullable=True
    )
    reference_resource_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    source_references: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    character: Mapped["Character"] = relationship(back_populates="variants")


class Location(Base, TimestampMixin):
    __tablename__ = "drama_locations"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_drama_location_project_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    spatial_layout: Mapped[str] = mapped_column(Text, default="", nullable=False)
    time_weather: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    lighting: Mapped[str] = mapped_column(Text, default="", nullable=False)
    color_palette: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    fixed_objects: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source_references: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    reference_resource_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    primary_resource_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("resources.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)

    project: Mapped["ShortDramaProject"] = relationship(back_populates="locations")


class Prop(Base, TimestampMixin):
    __tablename__ = "drama_props"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    appearance: Mapped[str] = mapped_column(Text, default="", nullable=False)
    appearance_scope: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    owner_character_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("drama_characters.id", ondelete="SET NULL"), nullable=True
    )
    continuity_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_references: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    reference_resource_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False, index=True)
    resource_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("resources.id", ondelete="SET NULL"), nullable=True
    )

    project: Mapped["ShortDramaProject"] = relationship(back_populates="props")


class CharacterRelationship(Base, TimestampMixin):
    __tablename__ = "character_relationships"
    __table_args__ = (
        UniqueConstraint("project_id", "source_character_id", "target_character_id", name="uq_character_relationship_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    source_character_id: Mapped[int] = mapped_column(Integer, ForeignKey("drama_characters.id", ondelete="CASCADE"), nullable=False, index=True)
    target_character_id: Mapped[int] = mapped_column(Integer, ForeignKey("drama_characters.id", ondelete="CASCADE"), nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(String(64), default="关联", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_references: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False, index=True)


class WorldCandidate(Base, TimestampMixin):
    __tablename__ = "world_candidates"
    __table_args__ = (Index("ix_world_candidates_project_status", "project_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    story_version_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("story_versions.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    conflicts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class CreativeJob(Base, TimestampMixin):
    __tablename__ = "creative_jobs"
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key", name="uq_creative_job_owner_idempotency"),
        Index("ix_creative_jobs_owner_status", "owner_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    job_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False, index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    output_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    logs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    parent_job_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("creative_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    provider_config_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ai_provider_configs.id", ondelete="SET NULL"), nullable=True, index=True)
    prompt_template_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ai_prompt_templates.id", ondelete="SET NULL"), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    token_usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0, nullable=False)


class AdaptationCandidate(Base, TimestampMixin):
    """尚未确认的改编候选；确认前不会改写当前剧本。"""

    __tablename__ = "adaptation_candidates"
    __table_args__ = (Index("ix_adaptation_candidates_project_status", "project_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chapter_start: Mapped[int] = mapped_column(Integer, nullable=False)
    chapter_end: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False, index=True)
    options: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    validation_errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    confirmed_option: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    confirmed_version_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("story_versions.id", ondelete="SET NULL"), nullable=True
    )


class SourceDocument(Base, TimestampMixin):
    """项目导入的原始文档及结构化解析摘要。"""

    __tablename__ = "source_documents"
    __table_args__ = (
        UniqueConstraint("project_id", "resource_id", name="uq_source_document_project_resource"),
        Index("ix_source_documents_project_status", "project_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_format: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    encoding: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False, index=True)
    total_chapters: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_paragraphs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_chars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    project: Mapped["ShortDramaProject"] = relationship(back_populates="source_documents")
    chapters: Mapped[list["SourceChapter"]] = relationship(
        back_populates="document", order_by="SourceChapter.sort_order", cascade="all, delete-orphan"
    )


class SourceChapter(Base, TimestampMixin):
    __tablename__ = "source_chapters"
    __table_args__ = (
        UniqueConstraint("document_id", "number", name="uq_source_chapter_document_number"),
        Index("ix_source_chapters_document_order", "document_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    paragraph_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    document: Mapped["SourceDocument"] = relationship(back_populates="chapters")
    paragraphs: Mapped[list["SourceParagraph"]] = relationship(
        back_populates="chapter", order_by="SourceParagraph.paragraph_index", cascade="all, delete-orphan"
    )


class SourceParagraph(Base, TimestampMixin):
    __tablename__ = "source_paragraphs"
    __table_args__ = (
        UniqueConstraint("chapter_id", "paragraph_index", name="uq_source_paragraph_chapter_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    chapter_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("source_chapters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paragraph_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_locator: Mapped[str] = mapped_column(String(128), default="", nullable=False)

    chapter: Mapped["SourceChapter"] = relationship(back_populates="paragraphs")


class ProjectResourceLink(Base, TimestampMixin):
    __tablename__ = "project_resource_links"
    __table_args__ = (Index("ix_project_resource_links_entity", "project_id", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(32), default="project", nullable=False)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ShotTaskLink(Base, TimestampMixin):
    __tablename__ = "shot_task_links"
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key", name="uq_shot_task_owner_idempotency"),
        Index("ix_shot_task_links_shot_status", "shot_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    shot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("drama_shots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False, index=True)
    take_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("drama_takes.id", ondelete="SET NULL"), nullable=True
    )
    purpose: Mapped[str] = mapped_column(String(32), default="generate", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="linked", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    output_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    sync_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sync_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)


__all__ = [
    "ShortDramaProject",
    "ProjectBrief",
    "Episode",
    "Scene",
    "StoryVersion",
    "Shot",
    "Take",
    "Character",
    "CharacterVariant",
    "Location",
    "Prop",
    "CharacterRelationship",
    "WorldCandidate",
    "StoryboardCandidate",
    "CreativeJob",
    "AdaptationCandidate",
    "SourceDocument",
    "SourceChapter",
    "SourceParagraph",
    "ProjectResourceLink",
    "ShotTaskLink",
]
