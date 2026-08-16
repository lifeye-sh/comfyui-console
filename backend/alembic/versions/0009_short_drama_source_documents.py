"""V2.1 source document structure.

Revision ID: 0009
Revises: 0008
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    expected = {"source_documents", "source_chapters", "source_paragraphs"}
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    present = expected & existing
    if present:
        missing = expected - present
        if missing:
            raise RuntimeError(f"V2.1 source document migration is incomplete; missing tables: {sorted(missing)}")
        return

    op.create_table(
        "source_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_id", sa.Integer(), sa.ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("source_format", sa.String(16), nullable=False),
        sa.Column("title", sa.String(255), server_default="", nullable=False),
        sa.Column("encoding", sa.String(32)),
        sa.Column("status", sa.String(24), server_default="pending", nullable=False),
        sa.Column("total_chapters", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_paragraphs", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_chars", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text()),
        *_timestamps(),
        sa.UniqueConstraint("project_id", "resource_id", name="uq_source_document_project_resource"),
    )
    op.create_index("ix_source_documents_owner_id", "source_documents", ["owner_id"])
    op.create_index("ix_source_documents_project_id", "source_documents", ["project_id"])
    op.create_index("ix_source_documents_resource_id", "source_documents", ["resource_id"])
    op.create_index("ix_source_documents_status", "source_documents", ["status"])
    op.create_index("ix_source_documents_project_status", "source_documents", ["project_id", "status"])

    op.create_table(
        "source_chapters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255)),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("paragraph_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("char_count", sa.Integer(), server_default="0", nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("document_id", "number", name="uq_source_chapter_document_number"),
    )
    op.create_index("ix_source_chapters_owner_id", "source_chapters", ["owner_id"])
    op.create_index("ix_source_chapters_document_id", "source_chapters", ["document_id"])
    op.create_index("ix_source_chapters_document_order", "source_chapters", ["document_id", "sort_order"])

    op.create_table(
        "source_paragraphs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("chapter_id", sa.Integer(), sa.ForeignKey("source_chapters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("paragraph_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source_locator", sa.String(128), server_default="", nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("chapter_id", "paragraph_index", name="uq_source_paragraph_chapter_index"),
    )
    op.create_index("ix_source_paragraphs_owner_id", "source_paragraphs", ["owner_id"])
    op.create_index("ix_source_paragraphs_chapter_id", "source_paragraphs", ["chapter_id"])


def downgrade() -> None:
    op.drop_table("source_paragraphs")
    op.drop_table("source_chapters")
    op.drop_table("source_documents")
