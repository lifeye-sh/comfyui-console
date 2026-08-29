"""Create V3 spatial plan and location view tables.

Revision ID: 0023
Revises: 0022
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v3_spatial_plan_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("location_stable_key", sa.String(length=64), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("drama_locations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("plan_kind", sa.String(length=16), nullable=False, server_default="exterior"),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="candidate"),
        sa.Column("name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("scale", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("topology", sa.JSON(), nullable=False),
        sa.Column("floor_plan", sa.JSON(), nullable=False),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("project_id", "location_stable_key", "version", name="uq_v3_spatial_key_ver"),
    )
    op.create_index("ix_v3_spatial_project_status", "v3_spatial_plan_versions", ["project_id", "status"])
    op.create_index("ix_v3_spatial_plan_versions_project_id", "v3_spatial_plan_versions", ["project_id"])

    op.create_table(
        "v3_location_view_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("spatial_plan_id", sa.Integer(), sa.ForeignKey("v3_spatial_plan_versions.id"), nullable=False),
        sa.Column("stable_key", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="candidate"),
        sa.Column("name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("view_angle", sa.String(length=96), nullable=False, server_default=""),
        sa.Column("resource_id", sa.Integer(), sa.ForeignKey("resources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("project_id", "stable_key", "version", name="uq_v3_locview_key_ver"),
    )
    op.create_index("ix_v3_locview_project_status", "v3_location_view_versions", ["project_id", "status"])
    op.create_index("ix_v3_locview_plan", "v3_location_view_versions", ["spatial_plan_id"])
    op.create_index("ix_v3_location_view_versions_project_id", "v3_location_view_versions", ["project_id"])


def downgrade() -> None:
    op.drop_table("v3_location_view_versions")
    op.drop_table("v3_spatial_plan_versions")