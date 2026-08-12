"""素材库无限级文件夹。"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "resource_folders" not in inspector.get_table_names():
        op.create_table(
            "resource_folders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("parent_id", sa.Integer(), sa.ForeignKey("resource_folders.id"), nullable=True),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("folder_type", sa.String(16), nullable=False, server_default="normal"),
            sa.Column("system_key", sa.String(128), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_resource_folders_owner_id", "resource_folders", ["owner_id"])
        op.create_index("ix_resource_folders_parent_id", "resource_folders", ["parent_id"])
        op.create_index("ix_resource_folders_system_key", "resource_folders", ["system_key"])
    resource_columns = {column["name"] for column in sa.inspect(bind).get_columns("resources")}
    if "folder_id" not in resource_columns:
        op.add_column("resources", sa.Column("folder_id", sa.Integer(), nullable=True))
        op.create_index("ix_resources_folder_id", "resources", ["folder_id"])


def downgrade() -> None:
    op.drop_index("ix_resources_folder_id", table_name="resources")
    op.drop_column("resources", "folder_id")
    op.drop_table("resource_folders")
