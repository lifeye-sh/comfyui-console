"""Store resource sizes large enough for 2GB uploads.

Revision ID: 0036_resource_size_bigint
Revises: 0035_structured_drama_imports
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0036_resource_size_bigint"
down_revision = "0035_structured_drama_imports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("resources") as batch:
        batch.alter_column("size", existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("resources") as batch:
        batch.alter_column("size", existing_type=sa.BigInteger(), type_=sa.Integer(), existing_nullable=False)
