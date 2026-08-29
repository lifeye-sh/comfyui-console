"""Create V3 character/prop anchor tables.

Revision ID: 0022
Revises: 0021
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v3_character_anchor_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("stable_key", sa.String(length=64), nullable=False),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("drama_characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("style_bible_id", sa.Integer(), sa.ForeignKey("v3_style_bible_versions.id"), nullable=True),
        sa.Column("generation_record_id", sa.Integer(), sa.ForeignKey("ai_generation_records.id"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="candidate"),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="supporting"),
        sa.Column("name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("identity_anchor", sa.JSON(), nullable=False),
        sa.Column("controllable_vars", sa.JSON(), nullable=False),
        sa.Column("drift_prohibition", sa.JSON(), nullable=False),
        sa.Column("expression_sheet", sa.JSON(), nullable=False),
        sa.Column("front_resource_id", sa.Integer(), sa.ForeignKey("resources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("side_resource_id", sa.Integer(), sa.ForeignKey("resources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("back_resource_id", sa.Integer(), sa.ForeignKey("resources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("project_id", "stable_key", "version", name="uq_v3_char_anchor_key_ver"),
    )
    op.create_index("ix_v3_char_anchor_project_status", "v3_character_anchor_versions", ["project_id", "status"])
    op.create_index("ix_v3_char_anchor_stable_key", "v3_character_anchor_versions", ["stable_key"])
    op.create_index("ix_v3_character_anchor_versions_project_id", "v3_character_anchor_versions", ["project_id"])

    op.create_table(
        "v3_character_state_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("character_stable_key", sa.String(length=64), nullable=False),
        sa.Column("anchor_version_id", sa.Integer(), sa.ForeignKey("v3_character_anchor_versions.id"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("scene_stable_key", sa.String(length=64), nullable=True),
        sa.Column("age_state", sa.String(length=96), nullable=False, server_default=""),
        sa.Column("costume", sa.Text(), nullable=False),
        sa.Column("hair_makeup", sa.Text(), nullable=False),
        sa.Column("injuries_dirt", sa.Text(), nullable=False),
        sa.Column("emotional_state", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("lighting_state", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("carried_props", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="candidate"),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_v3_char_state_project_key", "v3_character_state_versions", ["project_id", "character_stable_key"])

    op.create_table(
        "v3_prop_anchor_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("stable_key", sa.String(length=64), nullable=False),
        sa.Column("prop_id", sa.Integer(), sa.ForeignKey("drama_props.id", ondelete="SET NULL"), nullable=True),
        sa.Column("style_bible_id", sa.Integer(), sa.ForeignKey("v3_style_bible_versions.id"), nullable=True),
        sa.Column("generation_record_id", sa.Integer(), sa.ForeignKey("ai_generation_records.id"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="candidate"),
        sa.Column("name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("priority_rank", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("size", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("material", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("wear_condition", sa.Text(), nullable=False),
        sa.Column("owner_character_key", sa.String(length=64), nullable=True),
        sa.Column("state_changes", sa.JSON(), nullable=False),
        sa.Column("drift_prohibition", sa.JSON(), nullable=False),
        sa.Column("hero_shot_resource_id", sa.Integer(), sa.ForeignKey("resources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("project_id", "stable_key", "version", name="uq_v3_prop_anchor_key_ver"),
    )
    op.create_index("ix_v3_prop_anchor_project_status", "v3_prop_anchor_versions", ["project_id", "status"])
    op.create_index("ix_v3_prop_anchor_versions_project_id", "v3_prop_anchor_versions", ["project_id"])


def downgrade() -> None:
    op.drop_table("v3_prop_anchor_versions")
    op.drop_table("v3_character_state_versions")
    op.drop_table("v3_character_anchor_versions")