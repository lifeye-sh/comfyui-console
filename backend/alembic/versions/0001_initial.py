"""Initial schema frozen from repository baseline 84ebc43.

Do not import live ORM metadata here: later revisions own later tables/columns.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('generation_types',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('media_type', sa.String(length=16), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('default_workflow_id', sa.Integer(), nullable=True),
    sa.Column('param_template', sa.JSON(), nullable=False),
    sa.Column('menu_order', sa.Integer(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['default_workflow_id'], ['workflows.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_generation_types_code'), 'generation_types', ['code'], unique=True)
    op.create_table('nodes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('base_url', sa.String(length=255), nullable=False),
    sa.Column('ws_url', sa.String(length=255), nullable=True),
    sa.Column('tags', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('max_concurrent', sa.Integer(), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('settings',
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('value', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_table('workflows',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=True),
    sa.Column('generation_type_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('media_type', sa.String(length=16), nullable=False),
    sa.Column('tags', sa.JSON(), nullable=False),
    sa.Column('cover_resource_id', sa.Integer(), nullable=True),
    sa.Column('current_version_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['generation_type_id'], ['generation_types.id'], ),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_workflows_generation_type_id'), 'workflows', ['generation_type_id'], unique=False)
    op.create_table('audit_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('target_type', sa.String(length=32), nullable=True),
    sa.Column('target_id', sa.Integer(), nullable=True),
    sa.Column('detail', sa.Text(), nullable=True),
    sa.Column('ip', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)
    op.create_table('prompt_categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('resource_folders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('folder_type', sa.String(length=16), nullable=False),
    sa.Column('system_key', sa.String(length=128), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['parent_id'], ['resource_folders.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_resource_folders_owner_id'), 'resource_folders', ['owner_id'], unique=False)
    op.create_index(op.f('ix_resource_folders_parent_id'), 'resource_folders', ['parent_id'], unique=False)
    op.create_index(op.f('ix_resource_folders_system_key'), 'resource_folders', ['system_key'], unique=False)
    op.create_table('workflow_versions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('workflow_id', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('ui_json', sa.JSON(), nullable=True),
    sa.Column('api_json', sa.JSON(), nullable=False),
    sa.Column('param_schema', sa.JSON(), nullable=False),
    sa.Column('output_mapping', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('batches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('generation_type_id', sa.Integer(), nullable=True),
    sa.Column('workflow_version_id', sa.Integer(), nullable=True),
    sa.Column('global_params', sa.JSON(), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('is_template', sa.Boolean(), nullable=False),
    sa.Column('submitted_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['generation_type_id'], ['generation_types.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['workflow_version_id'], ['workflow_versions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('prompts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('negative_content', sa.Text(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('tags', sa.JSON(), nullable=False),
    sa.Column('remark', sa.Text(), nullable=False),
    sa.Column('cover_resource_id', sa.Integer(), nullable=True),
    sa.Column('visibility', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['prompt_categories.id'], ),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('resources',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=True),
    sa.Column('folder_id', sa.Integer(), nullable=True),
    sa.Column('media_type', sa.String(length=16), nullable=False),
    sa.Column('direction', sa.String(length=16), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('mime', sa.String(length=128), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=True),
    sa.Column('storage_key', sa.String(length=512), nullable=False),
    sa.Column('thumb_key', sa.String(length=512), nullable=True),
    sa.Column('width', sa.Integer(), nullable=True),
    sa.Column('height', sa.Integer(), nullable=True),
    sa.Column('duration', sa.Integer(), nullable=True),
    sa.Column('visibility', sa.String(length=16), nullable=False),
    sa.Column('meta', sa.JSON(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['folder_id'], ['resource_folders.id'], ),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_resources_folder_id'), 'resources', ['folder_id'], unique=False)
    op.create_index(op.f('ix_resources_sha256'), 'resources', ['sha256'], unique=False)
    op.create_table('shares',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('resource_id', sa.Integer(), nullable=False),
    sa.Column('token', sa.String(length=64), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=True),
    sa.Column('expires_at', sa.DateTime(), nullable=True),
    sa.Column('allow_download', sa.Boolean(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['resource_id'], ['resources.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_shares_resource_id'), 'shares', ['resource_id'], unique=False)
    op.create_index(op.f('ix_shares_token'), 'shares', ['token'], unique=True)
    op.create_table('tasks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('batch_id', sa.Integer(), nullable=False),
    sa.Column('row_no', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('generation_type_id', sa.Integer(), nullable=True),
    sa.Column('workflow_version_id', sa.Integer(), nullable=True),
    sa.Column('params', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('node_id', sa.Integer(), nullable=True),
    sa.Column('prompt_id', sa.String(length=128), nullable=True),
    sa.Column('retries', sa.Integer(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], ),
    sa.ForeignKeyConstraint(['generation_type_id'], ['generation_types.id'], ),
    sa.ForeignKeyConstraint(['node_id'], ['nodes.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['workflow_version_id'], ['workflow_versions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tasks_batch_id'), 'tasks', ['batch_id'], unique=False)
    op.create_index(op.f('ix_tasks_status'), 'tasks', ['status'], unique=False)
    op.create_table('task_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('task_id', sa.Integer(), nullable=False),
    sa.Column('type', sa.String(length=32), nullable=False),
    sa.Column('progress', sa.Integer(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_task_events_task_id'), 'task_events', ['task_id'], unique=False)
    op.create_table('task_resources',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('task_id', sa.Integer(), nullable=False),
    sa.Column('resource_id', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('slot_key', sa.String(length=64), nullable=True),
    sa.ForeignKeyConstraint(['resource_id'], ['resources.id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_task_resources_resource_id'), 'task_resources', ['resource_id'], unique=False)
    op.create_index(op.f('ix_task_resources_task_id'), 'task_resources', ['task_id'], unique=False)


def downgrade() -> None:
    op.drop_table('task_resources')
    op.drop_table('task_events')
    op.drop_table('tasks')
    op.drop_table('shares')
    op.drop_table('resources')
    op.drop_table('prompts')
    op.drop_table('batches')
    op.drop_table('workflow_versions')
    op.drop_table('resource_folders')
    op.drop_table('prompt_categories')
    op.drop_table('audit_logs')
    op.drop_table('workflows')
    op.drop_table('users')
    op.drop_table('settings')
    op.drop_table('nodes')
    op.drop_table('generation_types')
