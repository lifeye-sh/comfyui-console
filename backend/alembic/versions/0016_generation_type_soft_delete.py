"""Soft-delete unused generation types.

Revision ID: 0016
Revises: 0015
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("generation_types")}
    if "deleted_at" not in columns:
        op.add_column("generation_types", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    indexes = {item["name"] for item in inspector.get_indexes("generation_types")}
    if "ix_generation_types_deleted_at" not in indexes:
        op.create_index("ix_generation_types_deleted_at", "generation_types", ["deleted_at"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    indexes = {item["name"] for item in inspector.get_indexes("generation_types")}
    if "ix_generation_types_deleted_at" in indexes:
        op.drop_index("ix_generation_types_deleted_at", table_name="generation_types")
    columns = {item["name"] for item in inspector.get_columns("generation_types")}
    if "deleted_at" in columns:
        op.drop_column("generation_types", "deleted_at")
