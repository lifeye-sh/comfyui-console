"""Runtime monitoring fields and queue lookup indexes."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns("nodes")}
    if "last_probe_at" not in columns:
        op.add_column("nodes", sa.Column("last_probe_at", sa.DateTime(), nullable=True))
    if "consecutive_failures" not in columns:
        op.add_column("nodes", sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"))
    if "health_error" not in columns:
        op.add_column("nodes", sa.Column("health_error", sa.Text(), nullable=True))
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("tasks")}
    if "ix_tasks_status_node_id" not in indexes:
        op.create_index("ix_tasks_status_node_id", "tasks", ["status", "node_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_status_node_id", table_name="tasks")
    op.drop_column("nodes", "health_error")
    op.drop_column("nodes", "consecutive_failures")
    op.drop_column("nodes", "last_probe_at")
