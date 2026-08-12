"""工作流增加生成类型归属。"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    column_names = {column["name"] for column in sa.inspect(bind).get_columns("workflows")}
    if "generation_type_id" not in column_names:
        op.add_column("workflows", sa.Column("generation_type_id", sa.Integer(), nullable=True))
        op.create_index("ix_workflows_generation_type_id", "workflows", ["generation_type_id"])
    op.execute(sa.text("""
        UPDATE workflows
        SET generation_type_id = (
            SELECT generation_types.id
            FROM generation_types
            WHERE generation_types.default_workflow_id = workflows.id
            ORDER BY generation_types.id
            LIMIT 1
        )
        WHERE generation_type_id IS NULL
    """))
    op.execute(sa.text("""
        UPDATE workflows
        SET generation_type_id = (
            SELECT generation_types.id
            FROM generation_types
            WHERE generation_types.media_type = workflows.media_type
              AND generation_types.default_workflow_id IS NOT NULL
            ORDER BY generation_types.id
            LIMIT 1
        )
        WHERE generation_type_id IS NULL
          AND 1 = (
              SELECT COUNT(*)
              FROM generation_types
              WHERE generation_types.media_type = workflows.media_type
                AND generation_types.default_workflow_id IS NOT NULL
          )
    """))
    if "generation_type_id" not in column_names:
        with op.batch_alter_table("workflows") as batch_op:
            batch_op.create_foreign_key(
                "fk_workflows_generation_type_id",
                "generation_types",
                ["generation_type_id"],
                ["id"],
            )


def downgrade() -> None:
    with op.batch_alter_table("workflows") as batch_op:
        batch_op.drop_constraint("fk_workflows_generation_type_id", type_="foreignkey")
    op.drop_index("ix_workflows_generation_type_id", table_name="workflows")
    op.drop_column("workflows", "generation_type_id")
