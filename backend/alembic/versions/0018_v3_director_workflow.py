"""Create V3 director workflow tables.

Revision ID: 0018
Revises: 0017
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v3_stable_identities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("stable_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_from_type", sa.String(length=64), nullable=True),
        sa.Column("created_from_id", sa.Integer(), nullable=True),
        sa.Column("retired_at", sa.DateTime(), nullable=True),
        sa.Column("retired_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("project_id", "entity_type", "stable_key", name="uq_v3_identity_project_type_key"),
    )
    op.create_index("ix_v3_identity_project_type", "v3_stable_identities", ["project_id", "entity_type"])
    op.create_index("ix_v3_stable_identities_project_id", "v3_stable_identities", ["project_id"])
    op.create_index("ix_v3_stable_identities_status", "v3_stable_identities", ["status"])

    op.create_table(
        "v3_director_workflow_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("project_id", name="uq_v3_workflow_run_project"),
    )

    op.create_table(
        "v3_director_step_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workflow_run_id", sa.Integer(), sa.ForeignKey("v3_director_workflow_runs.id"), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("gate_status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("passed_at", sa.DateTime(), nullable=True),
        sa.Column("waive_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("workflow_run_id", "step", name="uq_v3_step_run_step"),
    )
    op.create_index("ix_v3_director_step_states_workflow_run_id", "v3_director_step_states", ["workflow_run_id"])

    op.create_table(
        "v3_approval_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("target_type", sa.String(length=48), nullable=False),
        sa.Column("target_ref", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="candidate"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("parent_approved_id", sa.Integer(), nullable=True),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_v3_approval_project_target", "v3_approval_decisions", ["project_id", "target_type", "target_ref"])
    op.create_index("ix_v3_approval_decisions_project_id", "v3_approval_decisions", ["project_id"])
    op.create_index("ix_v3_approval_decisions_status", "v3_approval_decisions", ["status"])


def downgrade() -> None:
    op.drop_table("v3_approval_decisions")
    op.drop_table("v3_director_step_states")
    op.drop_table("v3_director_workflow_runs")
    op.drop_table("v3_stable_identities")
