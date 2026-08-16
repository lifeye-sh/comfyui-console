"""V2.1 storyboard candidates, shot intent and media references.

Revision ID: 0012
Revises: 0011
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("drama_shots")}
    additions = (
        ("character_ids", sa.JSON(), None, sa.text("'[]'"), False),
        ("location_id", sa.Integer(), sa.ForeignKey("drama_locations.id", ondelete="SET NULL"), None, True),
        ("prop_ids", sa.JSON(), None, sa.text("'[]'"), False),
        ("mood", sa.String(255), None, "", False),
        ("composition", sa.String(255), None, "", False),
        ("transition", sa.String(128), None, "", False),
        ("first_frame_resource_id", sa.Integer(), sa.ForeignKey("resources.id", ondelete="SET NULL"), None, True),
        ("last_frame_resource_id", sa.Integer(), sa.ForeignKey("resources.id", ondelete="SET NULL"), None, True),
        ("pose_resource_id", sa.Integer(), sa.ForeignKey("resources.id", ondelete="SET NULL"), None, True),
        ("reference_video_resource_id", sa.Integer(), sa.ForeignKey("resources.id", ondelete="SET NULL"), None, True),
        ("reference_audio_resource_id", sa.Integer(), sa.ForeignKey("resources.id", ondelete="SET NULL"), None, True),
        ("reference_resource_ids", sa.JSON(), None, sa.text("'[]'"), False),
    )
    for name, type_, foreign_key, default, nullable in additions:
        if name not in columns:
            args = (foreign_key,) if foreign_key is not None else ()
            op.add_column("drama_shots", sa.Column(name, type_, *args, server_default=default, nullable=nullable))
    indexes = {item["name"] for item in inspector.get_indexes("drama_shots")}
    if "uq_drama_shots_scene_no" not in indexes:
        op.create_index("uq_drama_shots_scene_no", "drama_shots", ["scene_id", "shot_no"], unique=True)
    if "storyboard_candidates" not in inspector.get_table_names():
        op.create_table(
            "storyboard_candidates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("scene_id", sa.Integer(), sa.ForeignKey("drama_scenes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("story_version_id", sa.Integer(), sa.ForeignKey("story_versions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(24), server_default="pending", nullable=False),
            sa.Column("payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
            sa.Column("validation_warnings", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
            sa.Column("confirmed_mode", sa.String(24)), sa.Column("confirmed_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        for column in ("owner_id", "project_id", "scene_id", "story_version_id", "status"):
            op.create_index(f"ix_storyboard_candidates_{column}", "storyboard_candidates", [column])
        op.create_index("ix_storyboard_candidates_scene_status", "storyboard_candidates", ["scene_id", "status"])


def downgrade() -> None:
    op.drop_table("storyboard_candidates")
    op.drop_index("uq_drama_shots_scene_no", table_name="drama_shots")
    with op.batch_alter_table("drama_shots") as batch:
        for name in ("reference_resource_ids", "reference_audio_resource_id", "reference_video_resource_id", "pose_resource_id", "last_frame_resource_id", "first_frame_resource_id", "transition", "composition", "mood", "prop_ids", "location_id", "character_ids"):
            batch.drop_column(name)
