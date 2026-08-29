"""Create V3 dependency, manifest and audit tables.

Revision ID: 0024
Revises: 0023
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v3_artifact_dependencies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("downstream_type", sa.String(length=48), nullable=False),
        sa.Column("downstream_ref", sa.String(length=64), nullable=False),
        sa.Column("upstream_type", sa.String(length=48), nullable=False),
        sa.Column("upstream_ref", sa.String(length=64), nullable=False),
        sa.Column("dependency_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_v3_dep_project", "v3_artifact_dependencies", ["project_id"])
    op.create_index("ix_v3_dep_upstream", "v3_artifact_dependencies", ["upstream_type", "upstream_key" if False else "upstream_ref"])

    op.create_table(
        "v3_stale_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("asset_type", sa.String(length=48), nullable=False),
        sa.Column("asset_ref", sa.String(length=64), nullable=False),
        sa.Column("stale_reason", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("source_dependency_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("resolved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_v3_stale_project_status", "v3_stale_records", ["project_id", "status"])

    op.create_table(
        "v3_detected_gaps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("gap_type", sa.String(length=48), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("suggested_fix", sa.Text(), nullable=False),
        sa.Column("affected_refs", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_v3_gap_project_status", "v3_detected_gaps", ["project_id", "status"])

    op.create_table(
        "v3_generation_manifests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("style_bible_id", sa.Integer(), sa.ForeignKey("v3_style_bible_versions.id"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("project_id", "version", name="uq_v3_manifest_project_version"),
    )
    op.create_index("ix_v3_manifest_project_status", "v3_generation_manifests", ["project_id", "status"])

    op.create_table(
        "v3_manifest_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("manifest_id", sa.Integer(), sa.ForeignKey("v3_generation_manifests.id"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("asset_stable_key", sa.String(length=64), nullable=False),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("parent_key", sa.String(length=64), nullable=True),
        sa.Column("scenes", sa.JSON(), nullable=False),
        sa.Column("style_version_id", sa.Integer(), sa.ForeignKey("v3_style_bible_versions.id"), nullable=True),
        sa.Column("palette_version_id", sa.Integer(), sa.ForeignKey("v3_palette_versions.id"), nullable=True),
        sa.Column("reference_ids", sa.JSON(), nullable=False),
        sa.Column("required_view", sa.String(length=48), nullable=False, server_default=""),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("negative_constraints", sa.Text(), nullable=False),
        sa.Column("aspect_ratio", sa.String(length=16), nullable=False, server_default="9:16"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="planned"),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_v3_mi_manifest_status", "v3_manifest_items", ["manifest_id", "status"])
    op.create_index("ix_v3_mi_project_key", "v3_manifest_items", ["project_id", "asset_stable_key"])

    op.create_table(
        "v3_audit_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("manifest_version_id", sa.Integer(), sa.ForeignKey("v3_generation_manifests.id"), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="running"),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_v3_audit_project", "v3_audit_runs", ["project_id"])

    op.create_table(
        "v3_audit_issues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("v3_audit_runs.id"), nullable=False),
        sa.Column("dimension", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("affected_assets", sa.JSON(), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("waived_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("waive_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_v3_issue_run_severity", "v3_audit_issues", ["run_id", "severity"])


def downgrade() -> None:
    op.drop_table("v3_audit_issues")
    op.drop_table("v3_audit_runs")
    op.drop_table("v3_manifest_items")
    op.drop_table("v3_generation_manifests")
    op.drop_table("v3_detected_gaps")
    op.drop_table("v3_stale_records")
    op.drop_table("v3_artifact_dependencies")