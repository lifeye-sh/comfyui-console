"""Create V3 director conversation, context snapshot and action proposal tables.

Revision ID: 0027
Revises: 0026
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v3_context_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("revision_hash", sa.String(length=64), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("token_budget", sa.Integer(), nullable=False),
        sa.Column("token_estimated", sa.Integer(), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("truncation_note", sa.Text(), nullable=False),
        sa.Column("superseded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_v3_ctx_project_id", "v3_context_snapshots", ["project_id"])
    op.create_index("ix_v3_ctx_project_purpose", "v3_context_snapshots", ["project_id", "purpose"])
    op.create_index("ix_v3_ctx_revision", "v3_context_snapshots", ["revision_hash"])
    op.create_index("ix_v3_ctx_superseded", "v3_context_snapshots", ["superseded"])

    op.create_table(
        "v3_director_conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False, server_default="新对话"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("context_purpose", sa.String(length=32), nullable=False, server_default="chat"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_v3_conv_project_id", "v3_director_conversations", ["project_id"])
    op.create_index("ix_v3_conv_owner_id", "v3_director_conversations", ["owner_id"])
    op.create_index("ix_v3_conv_project_owner", "v3_director_conversations", ["project_id", "owner_id"])

    op.create_table(
        "v3_action_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id"), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("v3_director_conversations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("context_snapshot_id", sa.Integer(), sa.ForeignKey("v3_context_snapshots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action_type", sa.String(length=48), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_ref", sa.String(length=64), nullable=False),
        sa.Column("target_lock_version", sa.Integer(), nullable=False),
        sa.Column("base_revision_hash", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column("impact_refs", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("applied_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("apply_error", sa.Text(), nullable=False),
        sa.Column("dismissed_reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_v3_prop_project_id", "v3_action_proposals", ["project_id"])
    op.create_index("ix_v3_prop_owner_id", "v3_action_proposals", ["owner_id"])
    op.create_index("ix_v3_prop_project_status", "v3_action_proposals", ["project_id", "status"])

    op.create_table(
        "v3_director_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("v3_director_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("context_snapshot_id", sa.Integer(), sa.ForeignKey("v3_context_snapshots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("revision_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("proposal_id", sa.Integer(), sa.ForeignKey("v3_action_proposals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ai_meta", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_v3_msg_conversation_id", "v3_director_messages", ["conversation_id"])


def downgrade() -> None:
    op.drop_table("v3_director_messages")
    op.drop_table("v3_action_proposals")
    op.drop_table("v3_director_conversations")
    op.drop_table("v3_context_snapshots")