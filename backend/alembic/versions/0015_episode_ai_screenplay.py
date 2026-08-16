"""Episode AI screenplay candidates and locking.

Revision ID: 0015
Revises: 0014
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("drama_episodes")}
    for name, type_, default in (
        ("core_conflict", sa.Text(), "''"),
        ("emotional_arc", sa.Text(), "''"),
        ("opening_hook", sa.Text(), "''"),
        ("ending_hook", sa.Text(), "''"),
        ("is_locked", sa.Boolean(), sa.false()),
    ):
        if name not in columns:
            op.add_column("drama_episodes", sa.Column(name, type_, nullable=False, server_default=default))
    if "screenplay_revision_candidates" not in inspector.get_table_names():
        op.create_table(
            "screenplay_revision_candidates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("episode_id", sa.Integer(), sa.ForeignKey("drama_episodes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("generation_record_id", sa.Integer(), sa.ForeignKey("ai_generation_records.id", ondelete="SET NULL")),
            sa.Column("base_lock_version", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
            sa.Column("instruction", sa.Text(), nullable=False, server_default=""),
            sa.Column("content", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("validation_errors", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("confirmed_version_id", sa.Integer(), sa.ForeignKey("story_versions.id", ondelete="SET NULL")),
            sa.Column("confirmed_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    inspector = sa.inspect(op.get_bind())
    indexes = {item["name"] for item in inspector.get_indexes("screenplay_revision_candidates")}
    for name, fields in (
        ("ix_screenplay_revision_candidates_owner_id", ["owner_id"]),
        ("ix_screenplay_revision_candidates_project_id", ["project_id"]),
        ("ix_screenplay_revision_candidates_episode_id", ["episode_id"]),
        ("ix_screenplay_revision_candidates_status", ["status"]),
        ("ix_screenplay_revision_episode_status", ["episode_id", "status"]),
    ):
        if name not in indexes:
            op.create_index(name, "screenplay_revision_candidates", fields)


def downgrade() -> None:
    if "screenplay_revision_candidates" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("screenplay_revision_candidates")
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("drama_episodes")}
    with op.batch_alter_table("drama_episodes") as batch:
        for name in ("is_locked", "ending_hook", "opening_hook", "emotional_arc", "core_conflict"):
            if name in columns:
                batch.drop_column(name)
