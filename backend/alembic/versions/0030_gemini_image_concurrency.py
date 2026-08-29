"""Independent Gemini image concurrency.

Revision ID: 0030
Revises: 0029
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "image_provider_configs",
        sa.Column("max_concurrency", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("image_provider_configs", "max_concurrency")
