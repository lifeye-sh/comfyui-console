"""V2.1 short drama domain foundation.

Revision ID: 0008
Revises: 0007
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def owner_column() -> sa.Column:
    return sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False)


def upgrade() -> None:
    # 0001 使用当前 Base.metadata.create_all()。全新数据库在执行到 0008 前
    # 可能已经按当前模型创建了全部短剧表；旧数据库则没有这些表。
    # 两种路径都必须可升级，同时拒绝静默接受不完整的半迁移状态。
    expected_tables = {
        "short_drama_projects", "project_briefs", "drama_episodes", "drama_scenes",
        "story_versions", "drama_shots", "drama_takes", "drama_characters",
        "character_variants", "drama_locations", "drama_props", "creative_jobs",
        "project_resource_links", "shot_task_links",
    }
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
    existing_domain_tables = expected_tables & existing_tables
    if existing_domain_tables:
        missing_tables = expected_tables - existing_domain_tables
        if missing_tables:
            raise RuntimeError(f"V2.1 short drama migration is incomplete; missing tables: {sorted(missing_tables)}")
        return

    op.create_table(
        "short_drama_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        owner_column(),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("synopsis", sa.Text(), server_default="", nullable=False),
        sa.Column("source_type", sa.String(32), server_default="idea", nullable=False),
        sa.Column("status", sa.String(24), server_default="draft", nullable=False),
        sa.Column("stage", sa.String(32), server_default="brief", nullable=False),
        sa.Column("cover_resource_id", sa.Integer(), sa.ForeignKey("resources.id", ondelete="SET NULL")),
        sa.Column("settings", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("lock_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("deleted_at", sa.DateTime()),
        *timestamps(),
    )
    op.create_index("ix_short_drama_projects_owner_id", "short_drama_projects", ["owner_id"])
    op.create_index("ix_short_drama_projects_status", "short_drama_projects", ["status"])
    op.create_index("ix_short_drama_projects_deleted_at", "short_drama_projects", ["deleted_at"])
    op.create_index("ix_drama_projects_owner_status", "short_drama_projects", ["owner_id", "status"])

    op.create_table(
        "project_briefs",
        sa.Column("id", sa.Integer(), primary_key=True),
        owner_column(),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("genre", sa.String(64), server_default="", nullable=False),
        sa.Column("audience", sa.String(128), server_default="", nullable=False),
        sa.Column("tone", sa.String(128), server_default="", nullable=False),
        sa.Column("platform", sa.String(64), server_default="", nullable=False),
        sa.Column("aspect_ratio", sa.String(16), server_default="9:16", nullable=False),
        sa.Column("episode_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("episode_duration", sa.Integer(), server_default="60", nullable=False),
        sa.Column("quality_tier", sa.String(16), server_default="draft", nullable=False),
        sa.Column("visual_style", sa.Text(), server_default="", nullable=False),
        sa.Column("constraints", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("lock_version", sa.Integer(), server_default="1", nullable=False),
        *timestamps(),
    )
    op.create_index("ix_project_briefs_owner_id", "project_briefs", ["owner_id"])

    op.create_table(
        "drama_episodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        owner_column(),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(160), server_default="", nullable=False),
        sa.Column("synopsis", sa.Text(), server_default="", nullable=False),
        sa.Column("target_duration", sa.Integer(), server_default="60", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(24), server_default="draft", nullable=False),
        sa.Column("lock_version", sa.Integer(), server_default="1", nullable=False),
        *timestamps(),
        sa.UniqueConstraint("project_id", "number", name="uq_drama_episode_project_number"),
    )
    op.create_index("ix_drama_episodes_owner_id", "drama_episodes", ["owner_id"])
    op.create_index("ix_drama_episodes_status", "drama_episodes", ["status"])
    op.create_index("ix_drama_episodes_project_order", "drama_episodes", ["project_id", "sort_order"])

    op.create_table(
        "drama_characters",
        sa.Column("id", sa.Integer(), primary_key=True),
        owner_column(),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("aliases", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("identity", sa.Text(), server_default="", nullable=False),
        sa.Column("age_appearance", sa.String(128), server_default="", nullable=False),
        sa.Column("appearance", sa.Text(), server_default="", nullable=False),
        sa.Column("personality", sa.Text(), server_default="", nullable=False),
        sa.Column("relationships", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("negative_traits", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("primary_resource_id", sa.Integer(), sa.ForeignKey("resources.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(24), server_default="draft", nullable=False),
        *timestamps(),
        sa.UniqueConstraint("project_id", "name", name="uq_drama_character_project_name"),
    )
    op.create_index("ix_drama_characters_owner_id", "drama_characters", ["owner_id"])
    op.create_index("ix_drama_characters_project_id", "drama_characters", ["project_id"])

    op.create_table(
        "drama_locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        owner_column(),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("spatial_layout", sa.Text(), server_default="", nullable=False),
        sa.Column("time_weather", sa.String(255), server_default="", nullable=False),
        sa.Column("lighting", sa.Text(), server_default="", nullable=False),
        sa.Column("color_palette", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("fixed_objects", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("primary_resource_id", sa.Integer(), sa.ForeignKey("resources.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(24), server_default="draft", nullable=False),
        *timestamps(),
        sa.UniqueConstraint("project_id", "name", name="uq_drama_location_project_name"),
    )
    op.create_index("ix_drama_locations_owner_id", "drama_locations", ["owner_id"])
    op.create_index("ix_drama_locations_project_id", "drama_locations", ["project_id"])

    op.create_table(
        "story_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        owner_column(),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_version_id", sa.Integer(), sa.ForeignKey("story_versions.id")),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(160), server_default="", nullable=False),
        sa.Column("source", sa.String(32), server_default="manual", nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column("content", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default=sa.false(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("project_id", "version", name="uq_story_version_project_version"),
    )
    op.create_index("ix_story_versions_owner_id", "story_versions", ["owner_id"])
    op.create_index("ix_story_versions_project_id", "story_versions", ["project_id"])
    op.create_index(
        "uq_story_version_current_per_project", "story_versions", ["project_id"], unique=True,
        sqlite_where=sa.text("is_current = 1"), postgresql_where=sa.text("is_current"),
    )

    op.create_table(
        "drama_scenes",
        sa.Column("id", sa.Integer(), primary_key=True),
        owner_column(),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("drama_episodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scene_no", sa.String(32), server_default="", nullable=False),
        sa.Column("heading", sa.String(255), server_default="", nullable=False),
        sa.Column("location_name", sa.String(160), server_default="", nullable=False),
        sa.Column("time_of_day", sa.String(64), server_default="", nullable=False),
        sa.Column("interior_exterior", sa.String(16), server_default="", nullable=False),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("purpose", sa.Text(), server_default="", nullable=False),
        sa.Column("target_duration", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(24), server_default="draft", nullable=False),
        sa.Column("lock_version", sa.Integer(), server_default="1", nullable=False),
        *timestamps(),
    )
    op.create_index("ix_drama_scenes_owner_id", "drama_scenes", ["owner_id"])
    op.create_index("ix_drama_scenes_status", "drama_scenes", ["status"])
    op.create_index("ix_drama_scenes_episode_order", "drama_scenes", ["episode_id", "sort_order"])

    op.create_table(
        "character_variants",
        sa.Column("id", sa.Integer(), primary_key=True),
        owner_column(),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("drama_characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("wardrobe", sa.Text(), server_default="", nullable=False),
        sa.Column("hairstyle", sa.Text(), server_default="", nullable=False),
        sa.Column("makeup", sa.Text(), server_default="", nullable=False),
        sa.Column("primary_resource_id", sa.Integer(), sa.ForeignKey("resources.id", ondelete="SET NULL")),
        *timestamps(),
    )
    op.create_index("ix_character_variants_owner_id", "character_variants", ["owner_id"])
    op.create_index("ix_character_variants_character_id", "character_variants", ["character_id"])

    op.create_table(
        "drama_props",
        sa.Column("id", sa.Integer(), primary_key=True),
        owner_column(),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("owner_character_id", sa.Integer(), sa.ForeignKey("drama_characters.id", ondelete="SET NULL")),
        sa.Column("continuity_note", sa.Text(), server_default="", nullable=False),
        sa.Column("resource_id", sa.Integer(), sa.ForeignKey("resources.id", ondelete="SET NULL")),
        *timestamps(),
    )
    op.create_index("ix_drama_props_owner_id", "drama_props", ["owner_id"])
    op.create_index("ix_drama_props_project_id", "drama_props", ["project_id"])

    op.create_table(
        "drama_shots",
        sa.Column("id", sa.Integer(), primary_key=True),
        owner_column(),
        sa.Column("scene_id", sa.Integer(), sa.ForeignKey("drama_scenes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_story_version_id", sa.Integer(), sa.ForeignKey("story_versions.id")),
        sa.Column("shot_no", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.Text(), server_default="", nullable=False),
        sa.Column("visual_description", sa.Text(), server_default="", nullable=False),
        sa.Column("action", sa.Text(), server_default="", nullable=False),
        sa.Column("expression", sa.String(255), server_default="", nullable=False),
        sa.Column("dialogue", sa.Text(), server_default="", nullable=False),
        sa.Column("shot_size", sa.String(64), server_default="", nullable=False),
        sa.Column("camera_angle", sa.String(64), server_default="", nullable=False),
        sa.Column("camera_movement", sa.String(128), server_default="", nullable=False),
        sa.Column("duration", sa.Float(), server_default="0", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(24), server_default="draft", nullable=False),
        sa.Column("production_settings", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("lock_version", sa.Integer(), server_default="1", nullable=False),
        *timestamps(),
    )
    op.create_index("ix_drama_shots_owner_id", "drama_shots", ["owner_id"])
    op.create_index("ix_drama_shots_status", "drama_shots", ["status"])
    op.create_index("ix_drama_shots_scene_order", "drama_shots", ["scene_id", "sort_order"])

    op.create_table(
        "creative_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        owner_column(),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id", ondelete="CASCADE")),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), server_default="queued", nullable=False),
        sa.Column("progress", sa.Integer(), server_default="0", nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("input_payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("output_payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("logs", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("retries", sa.Integer(), server_default="0", nullable=False),
        sa.Column("heartbeat_at", sa.DateTime()),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("finished_at", sa.DateTime()),
        sa.Column("cancelled_at", sa.DateTime()),
        *timestamps(),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_creative_job_owner_idempotency"),
    )
    op.create_index("ix_creative_jobs_owner_id", "creative_jobs", ["owner_id"])
    op.create_index("ix_creative_jobs_project_id", "creative_jobs", ["project_id"])
    op.create_index("ix_creative_jobs_job_type", "creative_jobs", ["job_type"])
    op.create_index("ix_creative_jobs_status", "creative_jobs", ["status"])
    op.create_index("ix_creative_jobs_owner_status", "creative_jobs", ["owner_id", "status"])

    op.create_table(
        "project_resource_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        owner_column(),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_id", sa.Integer(), sa.ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("entity_type", sa.String(32), server_default="project", nullable=False),
        sa.Column("entity_id", sa.Integer()),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("metadata_snapshot", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        *timestamps(),
    )
    op.create_index("ix_project_resource_links_owner_id", "project_resource_links", ["owner_id"])
    op.create_index("ix_project_resource_links_project_id", "project_resource_links", ["project_id"])
    op.create_index("ix_project_resource_links_resource_id", "project_resource_links", ["resource_id"])
    op.create_index("ix_project_resource_links_entity", "project_resource_links", ["project_id", "entity_type", "entity_id"])

    op.create_table(
        "drama_takes",
        sa.Column("id", sa.Integer(), primary_key=True),
        owner_column(),
        sa.Column("shot_id", sa.Integer(), sa.ForeignKey("drama_shots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_id", sa.Integer(), sa.ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_task_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="SET NULL")),
        sa.Column("take_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), server_default="candidate", nullable=False),
        sa.Column("is_selected", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("generation_snapshot", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("review_note", sa.Text(), server_default="", nullable=False),
        *timestamps(),
        sa.UniqueConstraint("shot_id", "take_no", name="uq_drama_take_shot_number"),
    )
    op.create_index("ix_drama_takes_owner_id", "drama_takes", ["owner_id"])
    op.create_index("ix_drama_takes_status", "drama_takes", ["status"])
    op.create_index(
        "uq_drama_take_selected_per_shot", "drama_takes", ["shot_id"], unique=True,
        sqlite_where=sa.text("is_selected = 1"), postgresql_where=sa.text("is_selected"),
    )

    op.create_table(
        "shot_task_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        owner_column(),
        sa.Column("shot_id", sa.Integer(), sa.ForeignKey("drama_shots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("take_id", sa.Integer(), sa.ForeignKey("drama_takes.id", ondelete="SET NULL")),
        sa.Column("purpose", sa.String(32), server_default="generate", nullable=False),
        sa.Column("status", sa.String(24), server_default="linked", nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_shot_task_owner_idempotency"),
    )
    op.create_index("ix_shot_task_links_owner_id", "shot_task_links", ["owner_id"])
    op.create_index("ix_shot_task_links_shot_id", "shot_task_links", ["shot_id"])
    op.create_index("ix_shot_task_links_task_id", "shot_task_links", ["task_id"])
    op.create_index("ix_shot_task_links_shot_status", "shot_task_links", ["shot_id", "status"])


def downgrade() -> None:
    for table in (
        "shot_task_links",
        "drama_takes",
        "project_resource_links",
        "creative_jobs",
        "drama_shots",
        "drama_props",
        "character_variants",
        "drama_scenes",
        "story_versions",
        "drama_locations",
        "drama_characters",
        "drama_episodes",
        "project_briefs",
        "short_drama_projects",
    ):
        op.drop_table(table)
