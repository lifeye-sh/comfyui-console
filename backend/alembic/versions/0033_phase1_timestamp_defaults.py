"""Restore server timestamp defaults required by phase-one and director ORM inserts.

Revision ID: 0033
Revises: 0032
"""
from alembic import op
import sqlalchemy as sa

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

# Fixed revision-owned table list; never import evolving ORM metadata here.
TABLES = (
    "script_manifest_versions",
    "project_asset_versions",
    "shot_character_bindings",
    "v3_stable_identities",
    "v3_director_workflow_runs",
    "v3_director_step_states",
    "v3_approval_decisions",
    "v3_script_ledger_versions",
    "v3_story_beats",
    "v3_ledger_decisions",
    "v3_ledger_scenes",
    "v3_scene_character_appearances",
    "v3_scene_prop_states",
    "v3_continuity_facts",
    "v3_palette_versions",
    "v3_style_bible_versions",
    "v3_character_anchor_versions",
    "v3_character_state_versions",
    "v3_prop_anchor_versions",
    "v3_spatial_plan_versions",
    "v3_location_view_versions",
    "v3_artifact_dependencies",
    "v3_stale_records",
    "v3_detected_gaps",
    "v3_generation_manifests",
    "v3_manifest_items",
    "v3_audit_runs",
    "v3_audit_issues",
    "v3_manifest_references",
    "v3_audit_issue_targets",
    "v3_manifest_item_task_links",
    "v3_context_snapshots",
    "v3_director_conversations",
    "v3_action_proposals",
    "v3_director_messages",
)


def upgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            for column in ("created_at", "updated_at"):
                batch.alter_column(column, existing_type=sa.DateTime(), existing_nullable=False, server_default=sa.func.now())


def downgrade() -> None:
    for table in reversed(TABLES):
        with op.batch_alter_table(table) as batch:
            for column in ("created_at", "updated_at"):
                batch.alter_column(column, existing_type=sa.DateTime(), existing_nullable=False, server_default=None)
