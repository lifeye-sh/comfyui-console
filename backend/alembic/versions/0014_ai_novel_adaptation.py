"""AI novel analysis and adaptation infrastructure.

Revision ID: 0014
Revises: 0013
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def _index(table: str, name: str, columns: list[str]) -> None:
    if name not in {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}:
        op.create_index(name, table, columns)


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "ai_provider_configs" not in tables:
        op.create_table("ai_provider_configs",
            sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(128), nullable=False),
            sa.Column("provider", sa.String(32), nullable=False, server_default="openai_compatible"), sa.Column("base_url", sa.String(512), nullable=False),
            sa.Column("model", sa.String(128), nullable=False), sa.Column("api_key_encrypted", sa.Text(), nullable=False), sa.Column("api_key_hint", sa.String(32), nullable=False, server_default=""),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="120"), sa.Column("max_tokens", sa.Integer(), nullable=False, server_default="8192"),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("name", name="uq_ai_provider_name"))
    _index("ai_provider_configs", "ix_ai_provider_configs_enabled", ["enabled"]); _index("ai_provider_configs", "ix_ai_provider_configs_is_default", ["is_default"])

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "ai_prompt_templates" not in tables:
        op.create_table("ai_prompt_templates",
            sa.Column("id", sa.Integer(), primary_key=True), sa.Column("code", sa.String(64), nullable=False), sa.Column("name", sa.String(128), nullable=False), sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("system_prompt", sa.Text(), nullable=False), sa.Column("user_prompt", sa.Text(), nullable=False), sa.Column("response_schema", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("code", "version", name="uq_ai_prompt_code_version"))
    _index("ai_prompt_templates", "ix_ai_prompt_templates_code", ["code"]); _index("ai_prompt_templates", "ix_ai_prompt_templates_enabled", ["enabled"])

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "ai_generation_records" not in tables:
        op.create_table("ai_generation_records",
            sa.Column("id", sa.Integer(), primary_key=True), sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id", ondelete="CASCADE")),
            sa.Column("job_id", sa.Integer(), sa.ForeignKey("creative_jobs.id", ondelete="SET NULL")), sa.Column("provider_config_id", sa.Integer(), sa.ForeignKey("ai_provider_configs.id", ondelete="SET NULL")), sa.Column("prompt_template_id", sa.Integer(), sa.ForeignKey("ai_prompt_templates.id", ondelete="SET NULL")),
            sa.Column("operation", sa.String(64), nullable=False), sa.Column("model", sa.String(128), nullable=False, server_default=""), sa.Column("status", sa.String(24), nullable=False, server_default="running"),
            sa.Column("request_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")), sa.Column("response_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"), sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"), sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("estimated_cost", sa.Float(), nullable=False, server_default="0"), sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"), sa.Column("error", sa.Text()), sa.Column("finished_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
    for name, columns in (("ix_ai_generation_records_owner_id",["owner_id"]),("ix_ai_generation_records_project_id",["project_id"]),("ix_ai_generation_records_job_id",["job_id"]),("ix_ai_generation_records_operation",["operation"]),("ix_ai_generation_records_status",["status"]),("ix_ai_generation_owner_project",["owner_id","project_id"])): _index("ai_generation_records",name,columns)

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "novel_analysis_versions" not in tables:
        op.create_table("novel_analysis_versions",
            sa.Column("id", sa.Integer(), primary_key=True), sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("project_id", sa.Integer(), sa.ForeignKey("short_drama_projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False), sa.Column("generation_record_id", sa.Integer(), sa.ForeignKey("ai_generation_records.id", ondelete="SET NULL")),
            sa.Column("version", sa.Integer(), nullable=False), sa.Column("status", sa.String(24), nullable=False, server_default="candidate"), sa.Column("chapter_start", sa.Integer(), nullable=False), sa.Column("chapter_end", sa.Integer(), nullable=False),
            sa.Column("content", sa.JSON(), nullable=False, server_default=sa.text("'{}'")), sa.Column("validation_errors", sa.JSON(), nullable=False, server_default=sa.text("'[]'")), sa.Column("confirmed_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("project_id", "document_id", "version", name="uq_novel_analysis_version"))
    for name, columns in (("ix_novel_analysis_versions_owner_id",["owner_id"]),("ix_novel_analysis_versions_project_id",["project_id"]),("ix_novel_analysis_versions_document_id",["document_id"]),("ix_novel_analysis_project_status",["project_id","status"])): _index("novel_analysis_versions",name,columns)

    columns={item["name"] for item in sa.inspect(op.get_bind()).get_columns("creative_jobs")}
    for name,type_,default,nullable in (("parent_job_id",sa.Integer(),None,True),("provider_config_id",sa.Integer(),None,True),("prompt_template_id",sa.Integer(),None,True),("model",sa.String(128),None,True),("token_usage",sa.JSON(),sa.text("'{}'"),False),("estimated_cost",sa.Float(),"0",False)):
        if name not in columns: op.add_column("creative_jobs",sa.Column(name,type_,server_default=default,nullable=nullable))
    _index("creative_jobs","ix_creative_jobs_parent_job_id",["parent_job_id"]);_index("creative_jobs","ix_creative_jobs_provider_config_id",["provider_config_id"])


def downgrade() -> None:
    for name in ("ix_creative_jobs_provider_config_id","ix_creative_jobs_parent_job_id"):
        if name in {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("creative_jobs")}: op.drop_index(name,table_name="creative_jobs")
    columns={item["name"] for item in sa.inspect(op.get_bind()).get_columns("creative_jobs")}
    with op.batch_alter_table("creative_jobs") as batch:
        for name in ("estimated_cost","token_usage","model","prompt_template_id","provider_config_id","parent_job_id"):
            if name in columns: batch.drop_column(name)
    for table in ("novel_analysis_versions","ai_generation_records","ai_prompt_templates","ai_provider_configs"):
        if table in sa.inspect(op.get_bind()).get_table_names(): op.drop_table(table)
