"""V2.1 shot-task-take sync and compensation state.

Revision ID: 0013
Revises: 0012
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("shot_task_links")}
    additions = (
        ("output_payload", sa.JSON(), sa.text("'{}'"), False),
        ("sync_error", sa.Text(), None, True),
        ("sync_attempts", sa.Integer(), "0", False),
        ("next_retry_at", sa.DateTime(), None, True),
    )
    for name, type_, default, nullable in additions:
        if name not in columns:
            op.add_column("shot_task_links", sa.Column(name, type_, server_default=default, nullable=nullable))
    indexes = {item["name"] for item in inspector.get_indexes("shot_task_links")}
    if "ix_shot_task_links_next_retry_at" not in indexes:
        op.create_index("ix_shot_task_links_next_retry_at", "shot_task_links", ["next_retry_at"])
    take_indexes = {item["name"] for item in inspector.get_indexes("drama_takes")}
    if "uq_drama_take_task_resource" not in take_indexes:
        op.create_index("uq_drama_take_task_resource", "drama_takes", ["source_task_id", "resource_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_drama_take_task_resource", table_name="drama_takes")
    op.drop_index("ix_shot_task_links_next_retry_at", table_name="shot_task_links")
    with op.batch_alter_table("shot_task_links") as batch:
        for name in ("next_retry_at", "sync_attempts", "sync_error", "output_payload"):
            batch.drop_column(name)
