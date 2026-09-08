"""V2.1 world setting candidates, relationships and references.

Revision ID: 0011
Revises: 0010
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def _add_json(table: str, name: str, columns: set[str]) -> None:
    if name not in columns:
        op.add_column(table, sa.Column(name, sa.JSON(), server_default=sa.text("'[]'"), nullable=False))


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    scene_columns = {item["name"] for item in inspector.get_columns("drama_scenes")}
    _add_json("drama_scenes", "character_ids", scene_columns)
    if "location_id" not in scene_columns:
        with op.batch_alter_table("drama_scenes") as batch:
            batch.add_column(sa.Column("location_id", sa.Integer()))
            batch.create_foreign_key("fk_drama_scenes_location_id", "drama_locations", ["location_id"], ["id"], ondelete="SET NULL")
    for table in ("drama_characters", "character_variants", "drama_locations"):
        columns = {item["name"] for item in inspector.get_columns(table)}
        _add_json(table, "source_references", columns)
        _add_json(table, "reference_resource_ids", columns)
    prop_columns = {item["name"] for item in inspector.get_columns("drama_props")}
    if "appearance" not in prop_columns: op.add_column("drama_props", sa.Column("appearance", sa.Text(), server_default="", nullable=False))
    if "appearance_scope" not in prop_columns: op.add_column("drama_props", sa.Column("appearance_scope", sa.String(255), server_default="", nullable=False))
    _add_json("drama_props", "source_references", prop_columns)
    _add_json("drama_props", "reference_resource_ids", prop_columns)
    if "status" not in prop_columns:
        op.add_column("drama_props", sa.Column("status", sa.String(24), server_default="draft", nullable=False))
        op.create_index("ix_drama_props_status", "drama_props", ["status"])

    if "character_relationships" not in inspector.get_table_names():
        op.create_table(
            "character_relationships",
            sa.Column("id", sa.Integer(), primary_key=True), sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("source_character_id", sa.Integer(), sa.ForeignKey("drama_characters.id", ondelete="CASCADE"), nullable=False),
            sa.Column("target_character_id", sa.Integer(), sa.ForeignKey("drama_characters.id", ondelete="CASCADE"), nullable=False),
            sa.Column("relationship_type", sa.String(64), server_default="关联", nullable=False), sa.Column("description", sa.Text(), server_default="", nullable=False),
            sa.Column("source_references", sa.JSON(), server_default=sa.text("'[]'"), nullable=False), sa.Column("status", sa.String(24), server_default="draft", nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("project_id", "source_character_id", "target_character_id", name="uq_character_relationship_pair"),
        )
        for column in ("owner_id", "project_id", "source_character_id", "target_character_id", "status"):
            op.create_index(f"ix_character_relationships_{column}", "character_relationships", [column])
    if "world_candidates" not in inspector.get_table_names():
        op.create_table(
            "world_candidates",
            sa.Column("id", sa.Integer(), primary_key=True), sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("story_version_id", sa.Integer(), sa.ForeignKey("story_versions.id", ondelete="SET NULL")),
            sa.Column("status", sa.String(24), server_default="pending", nullable=False), sa.Column("payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
            sa.Column("conflicts", sa.JSON(), server_default=sa.text("'[]'"), nullable=False), sa.Column("confirmed_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        for column in ("owner_id", "project_id", "status"):
            op.create_index(f"ix_world_candidates_{column}", "world_candidates", [column])
        op.create_index("ix_world_candidates_project_status", "world_candidates", ["project_id", "status"])


def downgrade() -> None:
    op.drop_table("world_candidates"); op.drop_table("character_relationships")
    for table, columns in (("drama_props", ["status", "reference_resource_ids", "source_references", "appearance_scope", "appearance"]), ("drama_locations", ["reference_resource_ids", "source_references"]), ("character_variants", ["reference_resource_ids", "source_references"]), ("drama_characters", ["reference_resource_ids", "source_references"]), ("drama_scenes", ["location_id", "character_ids"])):
        with op.batch_alter_table(table) as batch:
            for column in columns: batch.drop_column(column)
