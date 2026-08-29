"""BigBanana phase-one script manifests and project asset versions.

Revision ID: 0028
Revises: 0027
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("drama_episodes", sa.Column("script_mode", sa.String(24), nullable=False, server_default="novel"))
    op.add_column("drama_episodes", sa.Column("script_text", sa.Text(), nullable=False, server_default=""))
    op.add_column("drama_episodes", sa.Column("script_settings", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("drama_episodes", sa.Column("script_revision", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("character_variants", sa.Column("status", sa.String(24), nullable=False, server_default="draft"))
    op.add_column("character_variants", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("character_variants", sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "script_manifest_versions",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("drama_episodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False), sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("source_script_revision", sa.Integer(), nullable=False), sa.Column("mode", sa.String(24), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""), sa.Column("total_duration", sa.Float(), nullable=False, server_default="0"),
        sa.Column("content", sa.JSON(), nullable=False), sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"), sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("episode_id", "version", name="uq_script_manifest_episode_version"),
    )
    op.create_index("ix_script_manifest_episode_status", "script_manifest_versions", ["episode_id", "status"])
    op.create_index("ix_script_manifest_versions_owner_id", "script_manifest_versions", ["owner_id"])
    op.create_index("ix_script_manifest_versions_project_id", "script_manifest_versions", ["project_id"])
    op.create_table(
        "project_asset_versions",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(24), nullable=False), sa.Column("entity_id", sa.Integer(), nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.Integer(), sa.ForeignKey("resources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_task_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"), sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("prompt", sa.Text(), nullable=False, server_default=""), sa.Column("generation_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("entity_type", "entity_id", "version", name="uq_project_asset_entity_version"),
    )
    op.create_index("ix_project_asset_project_entity", "project_asset_versions", ["project_id", "entity_type", "entity_id"])
    op.create_index("ix_project_asset_versions_owner_id", "project_asset_versions", ["owner_id"])
    op.create_table(
        "shot_character_bindings",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("shot_id", sa.Integer(), sa.ForeignKey("drama_shots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("drama_characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_id", sa.Integer(), sa.ForeignKey("character_variants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("inheritance_source", sa.String(24), nullable=False, server_default="character_default"),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("shot_id", "character_id", name="uq_shot_character_binding"),
    )


def downgrade() -> None:
    op.drop_table("shot_character_bindings")
    op.drop_table("project_asset_versions")
    op.drop_table("script_manifest_versions")
    op.drop_column("character_variants", "is_default"); op.drop_column("character_variants", "version"); op.drop_column("character_variants", "status")
    op.drop_column("drama_episodes", "script_revision"); op.drop_column("drama_episodes", "script_settings"); op.drop_column("drama_episodes", "script_text"); op.drop_column("drama_episodes", "script_mode")
