"""Gemini image size per model configuration.

Revision ID: 0031
Revises: 0030
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "image_provider_configs",
        sa.Column("image_size", sa.String(length=16), nullable=False, server_default="1024x1024"),
    )


def downgrade() -> None:
    op.drop_column("image_provider_configs", "image_size")
