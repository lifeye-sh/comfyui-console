"""Create V3 style bible and palette tables.

Revision ID: 0021
Revises: 0020
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v3_style_bible_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("palette_version_id", sa.Integer(), nullable=True),  # FK 后置（use_alter）
        sa.Column("generation_record_id", sa.Integer(), sa.ForeignKey("ai_generation_records.id"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="candidate"),
        sa.Column("name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("visual_thesis", sa.Text(), nullable=False),
        sa.Column("era", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("realism", sa.String(length=96), nullable=False, server_default=""),
        sa.Column("composition", sa.Text(), nullable=False),
        sa.Column("aspect_ratio", sa.String(length=16), nullable=False, server_default="9:16"),
        sa.Column("lens_language", sa.Text(), nullable=False),
        sa.Column("lighting", sa.Text(), nullable=False),
        sa.Column("texture_material", sa.Text(), nullable=False),
        sa.Column("sound_world", sa.Text(), nullable=False),
        sa.Column("non_negotiables", sa.JSON(), nullable=False),
        sa.Column("reference_ids", sa.JSON(), nullable=False),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("project_id", "version", name="uq_v3_style_project_version"),
    )
    op.create_index("ix_v3_style_project_status", "v3_style_bible_versions", ["project_id", "status"])
    op.create_index("ix_v3_style_bible_versions_project_id", "v3_style_bible_versions", ["project_id"])

    op.create_table(
        "v3_palette_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("style_bible_id", sa.Integer(), sa.ForeignKey("v3_style_bible_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=96), nullable=False, server_default=""),
        sa.Column("scope", sa.String(length=16), nullable=False, server_default="general"),
        sa.Column("time_variant", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("primary_color", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("secondary_color", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("accent_color", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("neutral_color", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("skin_tone_protection", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("forbidden_colors", sa.JSON(), nullable=False),
        sa.Column("exposure_notes", sa.Text(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_v3_palette_project", "v3_palette_versions", ["project_id"])
    # 补充 use_alter 外键
    with op.batch_alter_table("v3_style_bible_versions") as batch:
        batch.create_foreign_key(
            "fk_v3_style_palette_version", "v3_palette_versions",
            ["palette_version_id"], ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("v3_style_bible_versions") as batch:
        batch.drop_constraint("fk_v3_style_palette_version", type_="foreignkey")
    op.drop_table("v3_palette_versions")
    op.drop_table("v3_style_bible_versions")