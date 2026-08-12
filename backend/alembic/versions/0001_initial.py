"""initial — 创建 M1 全部表

Revision ID: 0001
Revises:
Create Date: 2026-08-05
"""
from __future__ import annotations

from alembic import op

import app.models  # noqa: F401  注册全部模型
from app.db import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # MVP：直接以模型元数据建表，保证与代码一致。
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())