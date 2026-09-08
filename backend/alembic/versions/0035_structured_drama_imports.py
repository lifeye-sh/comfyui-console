"""Add staged structured drama imports and shot prompt fields.

Revision ID: 0035_structured_drama_imports
Revises: 0034
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "0035_structured_drama_imports"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drama_structured_imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_key", sa.String(length=64), nullable=False),
        sa.Column("data_type", sa.String(length=24), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("parsed_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="previewed"),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "data_type", "checksum", name="uq_drama_structured_import_source"),
    )
    op.create_index("ix_drama_structured_imports_owner_id", "drama_structured_imports", ["owner_id"])
    op.create_index("ix_drama_structured_imports_project_id", "drama_structured_imports", ["project_id"])
    op.create_index("ix_drama_structured_imports_status", "drama_structured_imports", ["status"])
    op.create_index("ix_drama_structured_import_batch", "drama_structured_imports", ["project_id", "batch_key", "data_type"])
    with op.batch_alter_table("drama_shots") as batch:
        batch.add_column(sa.Column("timeline_storyboard", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("video_prompt", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("negative_prompt", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("continuity", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("drama_shots") as batch:
        batch.drop_column("continuity")
        batch.drop_column("negative_prompt")
        batch.drop_column("video_prompt")
        batch.drop_column("timeline_storyboard")
    op.drop_index("ix_drama_structured_import_batch", table_name="drama_structured_imports")
    op.drop_index("ix_drama_structured_imports_status", table_name="drama_structured_imports")
    op.drop_index("ix_drama_structured_imports_project_id", table_name="drama_structured_imports")
    op.drop_index("ix_drama_structured_imports_owner_id", table_name="drama_structured_imports")
    op.drop_table("drama_structured_imports")
