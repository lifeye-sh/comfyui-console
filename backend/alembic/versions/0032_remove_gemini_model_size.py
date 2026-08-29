"""Use maintained image-size options instead of per-model size.

Revision ID: 0032
Revises: 0031
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("image_provider_configs", "image_size")


def downgrade() -> None:
    op.add_column(
        "image_provider_configs",
        sa.Column("image_size", sa.String(length=16), nullable=False, server_default="1024x1024"),
    )
