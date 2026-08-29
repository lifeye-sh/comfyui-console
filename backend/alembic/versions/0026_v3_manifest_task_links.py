"""Create V3 manifest item task link table.

Revision ID: 0026
Revises: 0025
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v3_manifest_item_task_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("manifest_item_id", sa.Integer(), sa.ForeignKey("v3_manifest_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("output_resource_id", sa.Integer(), sa.ForeignKey("resources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("take_id", sa.Integer(), sa.ForeignKey("drama_takes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("generation_type_id", sa.Integer(), nullable=True),
        sa.Column("workflow_version_id", sa.Integer(), nullable=True),
        sa.Column("link_status", sa.String(length=16), nullable=False, server_default="linked"),
        sa.Column("sync_error", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_v3_mitl_owner_idem"),
    )
    op.create_index("ix_v3_mitl_owner_id", "v3_manifest_item_task_links", ["owner_id"])
    op.create_index("ix_v3_mitl_project_id", "v3_manifest_item_task_links", ["project_id"])
    op.create_index("ix_v3_mitl_item", "v3_manifest_item_task_links", ["manifest_item_id"])
    op.create_index("ix_v3_mitl_task", "v3_manifest_item_task_links", ["task_id"])
    op.create_index("ix_v3_mitl_link_status", "v3_manifest_item_task_links", ["link_status"])


def downgrade() -> None:
    op.drop_table("v3_manifest_item_task_links")