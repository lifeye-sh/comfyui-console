from alembic import op
import sqlalchemy as sa

revision = "0038_gallery_task_request"
down_revision = "0037_gallery_references"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("batches", sa.Column("request_key", sa.String(80), nullable=True))
    op.create_index("ux_batches_request_key", "batches", ["request_key"], unique=True)

def downgrade():
    op.drop_index("ux_batches_request_key", table_name="batches")
    op.drop_column("batches", "request_key")
