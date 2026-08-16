"""V2.1 screenplay workspace fields and adaptation candidates.

Revision ID: 0010
Revises: 0009
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    scene_columns = {item["name"] for item in inspector.get_columns("drama_scenes")}
    if "elements" not in scene_columns:
        op.add_column("drama_scenes", sa.Column("elements", sa.JSON(), server_default=sa.text("'[]'"), nullable=False))
    if "source_references" not in scene_columns:
        op.add_column("drama_scenes", sa.Column("source_references", sa.JSON(), server_default=sa.text("'[]'"), nullable=False))

    if "adaptation_candidates" not in inspector.get_table_names():
        op.create_table(
            "adaptation_candidates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False),
            sa.Column("chapter_start", sa.Integer(), nullable=False),
            sa.Column("chapter_end", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(24), server_default="pending", nullable=False),
            sa.Column("options", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
            sa.Column("validation_errors", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
            sa.Column("confirmed_option", sa.String(32)),
            sa.Column("confirmed_version_id", sa.Integer(), sa.ForeignKey("story_versions.id", ondelete="SET NULL")),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_adaptation_candidates_owner_id", "adaptation_candidates", ["owner_id"])
        op.create_index("ix_adaptation_candidates_project_id", "adaptation_candidates", ["project_id"])
        op.create_index("ix_adaptation_candidates_document_id", "adaptation_candidates", ["document_id"])
        op.create_index("ix_adaptation_candidates_status", "adaptation_candidates", ["status"])
        op.create_index("ix_adaptation_candidates_project_status", "adaptation_candidates", ["project_id", "status"])


def downgrade() -> None:
    op.drop_table("adaptation_candidates")
    with op.batch_alter_table("drama_scenes") as batch:
        batch.drop_column("source_references")
        batch.drop_column("elements")
