"""Alembic 迁移：新增 shares 与 audit_logs 表。"""
from __future__ import annotations

from alembic import op

import app.models  # noqa: F401
from app.db import Base

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.tables["shares"].create(op.get_bind(), checkfirst=True)
    Base.metadata.tables["audit_logs"].create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.tables["audit_logs"].drop(op.get_bind(), checkfirst=True)
    Base.metadata.tables["shares"].drop(op.get_bind(), checkfirst=True)