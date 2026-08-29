"""Create V3 story ledger tables.

Revision ID: 0019
Revises: 0018
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v3_script_ledger_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("source_documents.id"), nullable=True),
        sa.Column("analysis_id", sa.Integer(), sa.ForeignKey("novel_analysis_versions.id"), nullable=True),
        sa.Column("generation_record_id", sa.Integer(), sa.ForeignKey("ai_generation_records.id"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="candidate"),
        sa.Column("name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("project_id", "version", name="uq_v3_ledger_project_version"),
    )
    op.create_index("ix_v3_ledger_project_status", "v3_script_ledger_versions", ["project_id", "status"])
    op.create_index("ix_v3_script_ledger_versions_project_id", "v3_script_ledger_versions", ["project_id"])

    op.create_table(
        "v3_story_beats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ledger_id", sa.Integer(), sa.ForeignKey("v3_script_ledger_versions.id"), nullable=False),
        sa.Column("stable_key", sa.String(length=64), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("conflict", sa.Text(), nullable=False),
        sa.Column("reversal", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("causal_dependency", sa.String(length=64), nullable=True),
        sa.Column("characters", sa.JSON(), nullable=False),
        sa.Column("emotion_intensity", sa.Float(), nullable=False),
        sa.Column("emotion_valence", sa.Float(), nullable=False),
        sa.Column("dominant_emotion", sa.String(length=48), nullable=False, server_default=""),
        sa.Column("narrative_function", sa.String(length=96), nullable=False, server_default=""),
        sa.Column("evidence_type", sa.String(length=16), nullable=False, server_default="inferred"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source_locator", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("ledger_id", "stable_key", name="uq_v3_beat_ledger_key"),
    )
    op.create_index("ix_v3_beat_ledger_order", "v3_story_beats", ["ledger_id", "order"])
    op.create_index("ix_v3_story_beats_ledger_id", "v3_story_beats", ["ledger_id"])

    op.create_table(
        "v3_ledger_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("ledger_version_id", sa.Integer(), sa.ForeignKey("v3_script_ledger_versions.id"), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("chosen", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_v3_decision_project_status", "v3_ledger_decisions", ["project_id", "status"])


def downgrade() -> None:
    op.drop_table("v3_ledger_decisions")
    op.drop_table("v3_story_beats")
    op.drop_table("v3_script_ledger_versions")
