"""Alembic 迁移：新增提示词相关表。"""
from __future__ import annotations

from alembic import op

import app.models  # noqa: F401
from app.db import Base

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.tables["prompt_categories"].create(op.get_bind(), checkfirst=True)
    Base.metadata.tables["prompts"].create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.tables["prompts"].drop(op.get_bind(), checkfirst=True)
    Base.metadata.tables["prompt_categories"].drop(op.get_bind(), checkfirst=True)
