"""V2 generation type configuration versioning and task snapshots."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if "generation_type_config_versions" not in tables:
        op.create_table(
            "generation_type_config_versions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("generation_type_id", sa.Integer(), sa.ForeignKey("generation_types.id"), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
            sa.Column("config", sa.JSON(), nullable=False),
            sa.Column("validation_errors", sa.JSON(), nullable=False),
            sa.Column("source_version_id", sa.Integer(), sa.ForeignKey("generation_type_config_versions.id")),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id")),
            sa.Column("published_by", sa.Integer(), sa.ForeignKey("users.id")),
            sa.Column("published_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("generation_type_id", "version", name="uq_generation_type_config_version"),
        )
        op.create_index("ix_gt_config_generation_type_id", "generation_type_config_versions", ["generation_type_id"])
        op.create_index("ix_gt_config_status", "generation_type_config_versions", ["status"])

    generation_type_columns = {column["name"] for column in sa.inspect(bind).get_columns("generation_types")}
    if "published_config_version_id" not in generation_type_columns:
        op.add_column("generation_types", sa.Column("published_config_version_id", sa.Integer(), nullable=True))

    task_columns = {column["name"] for column in sa.inspect(bind).get_columns("tasks")}
    if "config_version_id" not in task_columns:
        op.add_column("tasks", sa.Column("config_version_id", sa.Integer(), nullable=True))
        op.create_index("ix_tasks_config_version_id", "tasks", ["config_version_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_config_version_id", table_name="tasks")
    op.drop_column("tasks", "config_version_id")
    op.drop_column("generation_types", "published_config_version_id")
    op.drop_table("generation_type_config_versions")
