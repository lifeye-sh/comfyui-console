"""Create V3 scene ledger tables.

Revision ID: 0020
Revises: 0019
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v3_ledger_scenes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("story_version_id", sa.Integer(), sa.ForeignKey("story_versions.id"), nullable=True),
        sa.Column("ledger_version_id", sa.Integer(), sa.ForeignKey("v3_script_ledger_versions.id"), nullable=True),
        sa.Column("stable_key", sa.String(length=64), nullable=False),
        sa.Column("scene_id", sa.Integer(), sa.ForeignKey("drama_scenes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("episode_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("heading", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("location_name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("time_of_day", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("interior_exterior", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("evidence_type", sa.String(length=16), nullable=False, server_default="inferred"),
        sa.Column("source_locator", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("alignment_status", sa.String(length=16), nullable=False, server_default="aligned"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("project_id", "stable_key", name="uq_v3_ledger_scene_key"),
    )
    op.create_index("ix_v3_ledger_scene_project_sv", "v3_ledger_scenes", ["project_id", "story_version_id"])
    op.create_index("ix_v3_ledger_scenes_project_id", "v3_ledger_scenes", ["project_id"])
    op.create_index("ix_v3_ledger_scenes_status", "v3_ledger_scenes", ["status"])

    op.create_table(
        "v3_scene_character_appearances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ledger_scene_id", sa.Integer(), sa.ForeignKey("v3_ledger_scenes.id"), nullable=False),
        sa.Column("character_stable_key", sa.String(length=64), nullable=False),
        sa.Column("character_name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("costume", sa.Text(), nullable=False),
        sa.Column("hair_makeup", sa.Text(), nullable=False),
        sa.Column("injuries_dirt", sa.Text(), nullable=False),
        sa.Column("emotional_state", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("change_from_previous", sa.Text(), nullable=False),
        sa.Column("evidence_type", sa.String(length=16), nullable=False, server_default="inferred"),
        sa.Column("source_locator", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("ledger_scene_id", "character_stable_key", name="uq_v3_app_scene_char"),
    )
    op.create_index("ix_v3_sca_ledger_scene_id", "v3_scene_character_appearances", ["ledger_scene_id"])

    op.create_table(
        "v3_scene_prop_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ledger_scene_id", sa.Integer(), sa.ForeignKey("v3_ledger_scenes.id"), nullable=False),
        sa.Column("prop_stable_key", sa.String(length=64), nullable=False),
        sa.Column("prop_name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("owner_character_key", sa.String(length=64), nullable=True),
        sa.Column("location_in_scene", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("condition", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("interaction", sa.Text(), nullable=False),
        sa.Column("state_change", sa.Text(), nullable=False),
        sa.Column("evidence_type", sa.String(length=16), nullable=False, server_default="inferred"),
        sa.Column("source_locator", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("ledger_scene_id", "prop_stable_key", name="uq_v3_propstate_scene_prop"),
    )
    op.create_index("ix_v3_sps_ledger_scene_id", "v3_scene_prop_states", ["ledger_scene_id"])

    op.create_table(
        "v3_continuity_facts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("story_version_id", sa.Integer(), sa.ForeignKey("story_versions.id"), nullable=True),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_key", sa.String(length=64), nullable=False),
        sa.Column("fact", sa.Text(), nullable=False),
        sa.Column("from_scene_key", sa.String(length=64), nullable=True),
        sa.Column("to_scene_key", sa.String(length=64), nullable=True),
        sa.Column("evidence_type", sa.String(length=16), nullable=False, server_default="inferred"),
        sa.Column("source_locator", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("resolution", sa.Text(), nullable=False),
        sa.Column("resolved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_v3_cf_project_severity", "v3_continuity_facts", ["project_id", "severity"])
    op.create_index("ix_v3_continuity_facts_project_id", "v3_continuity_facts", ["project_id"])
    op.create_index("ix_v3_continuity_facts_status", "v3_continuity_facts", ["status"])


def downgrade() -> None:
    op.drop_table("v3_continuity_facts")
    op.drop_table("v3_scene_prop_states")
    op.drop_table("v3_scene_character_appearances")
    op.drop_table("v3_ledger_scenes")
