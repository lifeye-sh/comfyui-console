"""Independent selected Takes for each frame and video."""
from alembic import op
import sqlalchemy as sa
revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("drama_takes", sa.Column("scope", sa.String(64), nullable=False, server_default="video"))
    op.drop_index("uq_drama_take_selected_per_shot", table_name="drama_takes")
    op.create_index("uq_drama_take_selected_per_scope", "drama_takes", ["shot_id", "scope"], unique=True, sqlite_where=sa.text("is_selected = 1"), postgresql_where=sa.text("is_selected"))

def downgrade():
    # Refuse lossy downgrade when multiple frame/video selections exist.
    count = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM (SELECT shot_id FROM drama_takes WHERE is_selected = true GROUP BY shot_id HAVING COUNT(*) > 1) x")).scalar()
    if count:
        raise RuntimeError("Cancel extra frame selections before downgrading")
    op.drop_index("uq_drama_take_selected_per_scope", table_name="drama_takes")
    op.drop_column("drama_takes", "scope")
    op.create_index("uq_drama_take_selected_per_shot", "drama_takes", ["shot_id"], unique=True, sqlite_where=sa.text("is_selected = 1"), postgresql_where=sa.text("is_selected"))
