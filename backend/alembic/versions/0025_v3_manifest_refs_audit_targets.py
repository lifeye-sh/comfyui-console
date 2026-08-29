"""Create V3 manifest reference and audit issue target tables.

Revision ID: 0025
Revises: 0024
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v3_manifest_references",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("manifest_item_id", sa.Integer(), sa.ForeignKey("v3_manifest_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reference_type", sa.String(length=32), nullable=False),
        sa.Column("reference_key", sa.String(length=64), nullable=False),
        sa.Column("reference_version_id", sa.Integer(), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="primary"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("manifest_item_id", "reference_type", "reference_key", name="uq_v3_mref_item_type_key"),
    )
    op.create_index("ix_v3_mref_item", "v3_manifest_references", ["manifest_item_id"])
    op.create_index("ix_v3_mref_type_key", "v3_manifest_references", ["reference_type", "reference_key"])

    op.create_table(
        "v3_audit_issue_targets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("audit_issue_id", sa.Integer(), sa.ForeignKey("v3_audit_issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_ref", sa.String(length=64), nullable=False),
        sa.Column("manifest_item_id", sa.Integer(), sa.ForeignKey("v3_manifest_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("audit_issue_id", "target_type", "target_ref", name="uq_v3_atgt_issue_type_ref"),
    )
    op.create_index("ix_v3_atgt_issue", "v3_audit_issue_targets", ["audit_issue_id"])
    op.create_index("ix_v3_atgt_type_ref", "v3_audit_issue_targets", ["target_type", "target_ref"])


def downgrade() -> None:
    op.drop_table("v3_audit_issue_targets")
    op.drop_table("v3_manifest_references")