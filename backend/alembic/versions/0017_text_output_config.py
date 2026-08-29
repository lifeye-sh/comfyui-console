"""Add text_output_config to workflow_versions.

Revision ID: 0017
Revises: 0016
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("workflow_versions")}
    if "text_output_config" not in columns:
        op.add_column("workflow_versions", sa.Column("text_output_config", sa.JSON(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("workflow_versions")}
    if "text_output_config" in columns:
        op.drop_column("workflow_versions", "text_output_config")
